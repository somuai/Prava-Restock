import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowsClockwise,
  BellSimpleRinging,
  Buildings,
  CalendarBlank,
  CaretDown,
  CaretRight,
  CaretUp,
  ChatCircleDots,
  Check,
  CheckCircle,
  Clock,
  ClockCounterClockwise,
  CreditCard,
  CurrencyInr,
  DownloadSimple,
  Eye,
  FileText,
  Fire,
  ForkKnife,
  Gauge,
  GlobeHemisphereEast,
  House,
  HourglassMedium,
  Lightning,
  ListBullets,
  LockKey,
  Package,
  Receipt,
  SealCheck,
  ShieldCheck,
  SignOut,
  SlackLogo,
  SpeakerHigh,
  SpeakerSlash,
  Sparkle,
  Stack,
  Storefront,
  Tag,
  Timer,
  UserCircle,
  UsersThree,
  Wallet,
  WhatsappLogo,
  X,
} from "@phosphor-icons/react";
import {
  ApiError,
  api,
  clearApiSessionToken,
  type AuditEntry,
  type Capabilities,
  type MerchantAddress,
  type MerchantCatalogProduct,
  type Notification,
  type TenantSummary,
  type TrackedItem,
  type UserProfile,
  type WorkflowRun,
} from "./api";
import { initializeNative } from "./native";
import { ParcelReveal3D, ProviderAward3D } from "./ParcelExperience";
import { GoogleSignIn } from "./GoogleSignIn";

type Track = "home" | "teams";
type View = Track | "activity";
type ProductTone = "attention" | "soon" | "watching";
export type ProductLifecycle = "attention" | "tracking" | "restocked";
type SoundKind = "hover" | "open" | "close" | "navigate" | "submit" | "confirm";

type PantryProduct = {
  id: string;
  itemId?: string;
  name: string;
  image: string;
  imageAlt: string;
  brand: string;
  category: string;
  size: string;
  tone: ProductTone;
  status: string;
  price: string;
  merchant: string;
  lastBought: string;
  daysRemaining: string;
  cadence: string;
  trigger: string;
  ingredients: string;
  nutrition: string;
  lifecycle: ProductLifecycle;
  nextDue: string;
};

type SubscriptionProduct = {
  id: string;
  itemId?: string;
  name: string;
  category: string;
  logo: string;
  color: string;
  currentPlan: string;
  currentAmount: string;
  alternatePlan: string;
  alternateAmount: string;
  renewal: string;
  cadence: string;
  owner: string;
  savings: string;
  status: string;
  note: string;
  description: string;
  currency: "USD" | "INR";
  priceBasis: string;
  quantity: string;
  usage: string;
  usageDetail: string;
  paymentMethod: string;
  invoiceStatus: string;
  planFeatures: string[];
  alternateDescription: string;
};

export type ProviderBrand = {
  name: string;
  logo: string;
  accent: string;
  wide?: boolean;
};

const providerBrands: Array<ProviderBrand & { matches: string[] }> = [
  { name: "Zepto", logo: "/app/assets/providers/zepto.svg", accent: "#7b1fa2", wide: true, matches: ["zepto"] },
  { name: "GitHub Copilot", logo: "/app/assets/providers/githubcopilot.svg", accent: "#24292f", matches: ["github", "copilot"] },
  { name: "Vercel", logo: "/app/assets/providers/vercel.svg", accent: "#111111", matches: ["vercel"] },
  { name: "Figma", logo: "/app/assets/providers/figma.svg", accent: "#a259ff", matches: ["figma"] },
  { name: "Railway", logo: "/app/assets/providers/railway.svg", accent: "#6c4cf1", matches: ["railway"] },
  { name: "Notion", logo: "/app/assets/providers/notion.svg", accent: "#111111", matches: ["notion"] },
  { name: "Netflix", logo: "/app/assets/providers/netflix.svg", accent: "#e50914", matches: ["netflix"] },
];

export function providerBrandForName(provider: string): ProviderBrand | null {
  const normalized = provider.trim().toLowerCase();
  const match = providerBrands.find((brand) => brand.matches.some((candidate) => normalized.includes(candidate)));
  if (!match) return null;
  const { matches: _matches, ...brand } = match;
  return brand;
}

const previews: Notification[] = [
  {
    notification_id: "preview-home",
    run_id: "preview-home",
    track: "home",
    message: "You'll run out of Arabica coffee in 2 days, and it dropped to ₹380 — below your ₹400 threshold. Reorder from Zepto?",
    actions: ["approve", "adjust", "skip"],
    status: "preview",
  },
  {
    notification_id: "preview-teams",
    run_id: "preview-teams",
    track: "teams",
    message: "GitHub Copilot Business renews in 2 days. Renew for $39 or explicitly switch to the $32 annual plan?",
    actions: ["renew_as_is", "switch_plan", "skip"],
    status: "preview",
  },
];

function initialViewFromUrl(): View {
  const requested = new URLSearchParams(window.location.search).get("view");
  return requested === "teams" || requested === "activity" ? requested : "home";
}

function reviewerShowcaseFromUrl(): boolean {
  return new URLSearchParams(window.location.search).get("review") === "showcase";
}

const products: PantryProduct[] = [
  {
    id: "coffee",
    itemId: "00000000-0000-0000-0000-000000000101",
    name: "Attikan Estate coffee",
    image: "/app/assets/product-coffee-attikan-cutout.png",
    imageAlt: "Blue Tokai Attikan Estate coffee pouch",
    brand: "Blue Tokai",
    category: "Coffee",
    size: "500 g",
    tone: "attention",
    status: "2 days left",
    price: "₹380",
    merchant: "Zepto",
    lastBought: "28 June 2026",
    daysRemaining: "about 2 days",
    cadence: "every 21 days",
    trigger: "Depletion and price threshold",
    ingredients: "100% Arabica coffee",
    nutrition: "No additives. Roast profile and tasting notes come from the merchant listing.",
    lifecycle: "attention",
    nextDue: "21 days after a completed purchase",
  },
  {
    id: "milk",
    name: "Amul Taaza milk",
    image: "/app/assets/product-amul-taaza.png",
    imageAlt: "Amul Taaza milk pouch",
    brand: "Amul",
    category: "Dairy",
    size: "1 L",
    tone: "soon",
    status: "4 days left",
    price: "₹57",
    merchant: "Zepto",
    lastBought: "13 July 2026",
    daysRemaining: "about 4 days",
    cadence: "every 7 days",
    trigger: "Predicted depletion",
    ingredients: "Toned milk",
    nutrition: "Approx. 3% fat and 8.5% solids-not-fat; verify the current pack before purchase.",
    lifecycle: "attention",
    nextDue: "about 7 days after a completed purchase",
  },
  {
    id: "paper",
    itemId: "00000000-0000-0000-0000-000000000103",
    name: "JK A4 copier paper",
    image: "/app/assets/product-jk-paper-cutout.png",
    imageAlt: "JK A4 copier paper ream",
    brand: "JK Paper",
    category: "Home office",
    size: "500 sheets",
    tone: "watching",
    status: "Bought yesterday",
    price: "₹650",
    merchant: "Zepto",
    lastBought: "2 July 2026",
    daysRemaining: "about 44 days",
    cadence: "every 45 days",
    trigger: "Predicted depletion",
    ingredients: "75 GSM copier paper",
    nutrition: "Not applicable. Restock tracks pack size, paper weight, and exact SKU.",
    lifecycle: "restocked",
    nextDue: "in about 44 days",
  },
  {
    id: "filter",
    itemId: "00000000-0000-0000-0000-000000000102",
    name: "Aquaguard filter kit",
    image: "/app/assets/product-aquaguard-filter.png",
    imageAlt: "Aquaguard replacement filter kit",
    brand: "Eureka Forbes",
    category: "Home care",
    size: "2-piece kit",
    tone: "soon",
    status: "Due in 5 days",
    price: "₹799",
    merchant: "Eureka Forbes",
    lastBought: "20 January 2026",
    daysRemaining: "about 5 days",
    cadence: "every 180 days",
    trigger: "Known replacement date",
    ingredients: "Sediment and carbon filter cartridges",
    nutrition: "Not applicable. Restock preserves the exact purifier-compatible part number.",
    lifecycle: "attention",
    nextDue: "180 days after a completed replacement",
  },
  {
    id: "oil",
    name: "Figaro olive oil",
    image: "/app/assets/product-figaro-oil-cutout.png",
    imageAlt: "Figaro extra virgin olive oil bottle",
    brand: "Figaro",
    category: "Pantry",
    size: "1 L",
    tone: "watching",
    status: "11 days left",
    price: "₹899",
    merchant: "Zepto",
    lastBought: "14 June 2026",
    daysRemaining: "about 11 days",
    cadence: "every 45 days",
    trigger: "Predicted depletion",
    ingredients: "Extra virgin olive oil",
    nutrition: "Fat-based pantry staple. Confirm current label and pack size before approving.",
    lifecycle: "tracking",
    nextDue: "in about 11 days",
  },
  {
    id: "salt",
    name: "Tata Salt",
    image: "/app/assets/product-tata-salt-cutout.png",
    imageAlt: "Tata Salt one kilogram pouch",
    brand: "Tata",
    category: "Pantry",
    size: "1 kg",
    tone: "watching",
    status: "17 days left",
    price: "₹30",
    merchant: "Zepto",
    lastBought: "16 July 2026",
    daysRemaining: "about 17 days",
    cadence: "every 30 days",
    trigger: "Predicted depletion",
    ingredients: "Vacuum-evaporated iodised salt",
    nutrition: "Iodised pantry staple. Restock keeps the exact pack size and merchant listing attached.",
    lifecycle: "tracking",
    nextDue: "in about 17 days",
  },
  {
    id: "detergent",
    name: "Surf Excel detergent",
    image: "/app/assets/product-surf-excel-cutout.png",
    imageAlt: "Surf Excel detergent powder pouch",
    brand: "Surf Excel",
    category: "Home care",
    size: "500 g",
    tone: "soon",
    status: "6 days left",
    price: "₹145",
    merchant: "Zepto",
    lastBought: "30 June 2026",
    daysRemaining: "about 6 days",
    cadence: "every 35 days",
    trigger: "Predicted depletion",
    ingredients: "Laundry detergent powder",
    nutrition: "Not applicable. Restock preserves the exact pack and never substitutes a different detergent silently.",
    lifecycle: "attention",
    nextDue: "in about 6 days",
  },
  {
    id: "toothpaste",
    itemId: "00000000-0000-0000-0000-000000000104",
    name: "Colgate Strong Teeth",
    image: "/app/assets/product-colgate-strong-teeth-cutout.png",
    imageAlt: "Colgate Strong Teeth toothpaste box",
    brand: "Colgate",
    category: "Personal care",
    size: "200 g",
    tone: "watching",
    status: "9 days left",
    price: "₹119",
    merchant: "Zepto",
    lastBought: "23 June 2026",
    daysRemaining: "about 9 days",
    cadence: "every 45 days",
    trigger: "Predicted depletion",
    ingredients: "Anticavity toothpaste",
    nutrition: "Personal-care staple. Restock tracks the exact Strong Teeth SKU and pack size.",
    lifecycle: "tracking",
    nextDue: "in about 9 days",
  },
];

const subscriptions: SubscriptionProduct[] = [
  {
    id: "copilot",
    itemId: "00000000-0000-0000-0000-000000000105",
    name: "GitHub Copilot Business",
    category: "Developer tool",
    logo: "/app/assets/providers/githubcopilot.svg",
    color: "#111111",
    currentPlan: "Business monthly",
    currentAmount: "$39",
    alternatePlan: "Business annual",
    alternateAmount: "$32",
    renewal: "31 July",
    cadence: "Monthly",
    owner: "Engineering",
    savings: "$84 / year",
    status: "Decision due",
    note: "The plan switch is a separate, explicit decision. A normal renewal can never select it silently.",
    description: "AI coding assistance managed for the Engineering workspace, with organization-level access and policy controls.",
    currency: "USD",
    priceBasis: "tracked monthly total",
    quantity: "Organization workspace",
    usage: "Within Restock budget",
    usageDetail: "The spend cap is checked in code before Prava is called.",
    paymentMethod: "Prava approval required",
    invoiceStatus: "Approval due",
    planFeatures: ["Organization-managed access", "Policy-controlled workspace", "Usage visible to billing owners"],
    alternateDescription: "Move the same tracked workspace to annual billing after a separate plan-change approval.",
  },
  {
    id: "vercel",
    name: "Vercel Pro",
    category: "Cloud",
    logo: "/app/assets/providers/vercel.svg",
    color: "#111111",
    currentPlan: "Pro",
    currentAmount: "$20",
    alternatePlan: "Keep current",
    alternateAmount: "$20",
    renewal: "8 August",
    cadence: "Monthly",
    owner: "Product",
    savings: "No cheaper match",
    status: "Watching",
    note: "Restock watches the renewal date and presents a choice only when there is a meaningful alternative.",
    description: "Collaborative deployment and managed frontend infrastructure for the Product workspace.",
    currency: "USD",
    priceBasis: "tracked monthly total",
    quantity: "Team workspace",
    usage: "Usage-based services",
    usageDetail: "The final vendor amount must be revalidated before approval.",
    paymentMethod: "Prava approval when due",
    invoiceStatus: "Not due",
    planFeatures: ["Team deployments", "Usage-based resources", "Spend visibility"],
    alternateDescription: "No validated alternate plan is attached to this tracked subscription.",
  },
  {
    id: "figma",
    name: "Figma Professional",
    category: "Design",
    logo: "/app/assets/providers/figma.svg",
    color: "#a259ff",
    currentPlan: "Professional",
    currentAmount: "$15",
    alternatePlan: "Keep current",
    alternateAmount: "$15",
    renewal: "14 August",
    cadence: "Monthly",
    owner: "Engineering",
    savings: "No action needed",
    status: "Watching",
    note: "Seat counts and invoices remain code-owned facts; the model never invents a billing decision.",
    description: "A collaborative design workspace for shared files, libraries, and team review.",
    currency: "USD",
    priceBasis: "tracked monthly total",
    quantity: "Professional workspace",
    usage: "Seat detail awaited",
    usageDetail: "Restock only displays a seat count after it is sourced from billing.",
    paymentMethod: "Prava approval when due",
    invoiceStatus: "Not due",
    planFeatures: ["Shared design files", "Team libraries", "Workspace permissions"],
    alternateDescription: "No validated alternate plan is attached to this tracked subscription.",
  },
  {
    id: "railway",
    name: "Railway Hobby",
    category: "Infrastructure",
    logo: "/app/assets/providers/railway.svg",
    color: "#6c45f7",
    currentPlan: "Hobby",
    currentAmount: "$5+",
    alternatePlan: "Usage review",
    alternateAmount: "Variable",
    renewal: "18 August",
    cadence: "Monthly",
    owner: "Infrastructure",
    savings: "Review usage",
    status: "Watching",
    note: "Variable invoices are revalidated before approval so an old estimate cannot become a charge.",
    description: "Usage-based project infrastructure tracked for the Infrastructure workspace.",
    currency: "USD",
    priceBasis: "base plan plus usage",
    quantity: "Infrastructure workspace",
    usage: "Variable invoice",
    usageDetail: "Restock requests a fresh amount before every payment decision.",
    paymentMethod: "Prava approval when due",
    invoiceStatus: "Estimate only",
    planFeatures: ["Project environments", "Usage-based resources", "Current-cycle cost review"],
    alternateDescription: "Review the fresh usage quote before changing or paying this plan.",
  },
  {
    id: "notion",
    name: "Notion Plus",
    category: "Workspace",
    logo: "/app/assets/providers/notion.svg",
    color: "#111111",
    currentPlan: "Plus",
    currentAmount: "$12",
    alternatePlan: "Annual",
    alternateAmount: "$10",
    renewal: "2 September",
    cadence: "Monthly",
    owner: "Operations",
    savings: "$24 / year",
    status: "Watching",
    note: "Restock can prepare a plan comparison; the switch still waits for the dedicated action.",
    description: "A shared operations workspace with expanded collaboration and workspace controls.",
    currency: "USD",
    priceBasis: "tracked monthly total",
    quantity: "Operations workspace",
    usage: "Within Restock budget",
    usageDetail: "A fresh billing summary is required before any annual switch.",
    paymentMethod: "Prava approval when due",
    invoiceStatus: "Not due",
    planFeatures: ["Team workspace", "Shared permissions", "Workspace history"],
    alternateDescription: "Switch the tracked workspace to annual billing after an explicit plan-change review.",
  },
  {
    id: "netflix",
    name: "Netflix Standard",
    category: "Team benefit",
    logo: "/app/assets/providers/netflix.svg",
    color: "#e50914",
    currentPlan: "Standard",
    currentAmount: "₹499",
    alternatePlan: "Keep current",
    alternateAmount: "₹499",
    renewal: "9 September",
    cadence: "Monthly",
    owner: "People",
    savings: "No cheaper match",
    status: "Watching",
    note: "Entertainment appears in Teams only when the organization funds it as a shared benefit.",
    description: "A shared entertainment benefit tracked as an organization-funded subscription.",
    currency: "INR",
    priceBasis: "tracked monthly total",
    quantity: "One shared benefit",
    usage: "Fixed plan",
    usageDetail: "No plan change is suggested without a sourced vendor comparison.",
    paymentMethod: "Prava approval when due",
    invoiceStatus: "Not due",
    planFeatures: ["Shared team benefit", "Monthly renewal tracking", "Explicit payment approval"],
    alternateDescription: "No validated alternate plan is attached to this tracked subscription.",
  },
];

// These are the five stable reviewer fixtures from triggers/seed_data.json.
// They deliberately use exact opaque SKU identifiers—not name matching—so a
// real user's arbitrary persisted item can never inherit a made-up pack shot
// or provider identity. Values returned by the API still own amount, cadence,
// trigger state, merchant, and renewal details.
const reviewerHomePresentationIds: Record<string, PantryProduct["id"]> = {
  "zepto-arabica-coffee-500g": "coffee",
  "zepto-ro-filter-cartridge": "filter",
  "swiggy-a4-paper-500": "paper",
  "zepto-toothpaste-twin-pack": "toothpaste",
};

const reviewerTeamPresentationIds: Record<string, SubscriptionProduct["id"]> = {
  "teamtool-pro-monthly": "copilot",
};

const pantryProductById = new Map(products.map((product) => [product.id, product]));
const subscriptionById = new Map(subscriptions.map((subscription) => [subscription.id, subscription]));

export function reviewerHomeProductPresentation(merchantSkuId: string): PantryProduct | undefined {
  const productId = reviewerHomePresentationIds[merchantSkuId];
  return productId ? pantryProductById.get(productId) : undefined;
}

export function reviewerTeamSubscriptionPresentation(
  merchantSkuId: string,
): SubscriptionProduct | undefined {
  const subscriptionId = reviewerTeamPresentationIds[merchantSkuId];
  return subscriptionId ? subscriptionById.get(subscriptionId) : undefined;
}

/**
 * The temporary reviewer account is a deliberate, isolated walkthrough
 * surface. It restores the original shelf composition from the demo rather
 * than showing generic Restock marks for its five workflow fixtures. Only
 * those persisted fixtures receive an itemId; the remaining objects are
 * presentation-only so they cannot create a workflow or payment action.
 */
export function reviewerShowcaseProducts(items: TrackedItem[]): PantryProduct[] {
  const itemByPresentationId = new Map<string, TrackedItem>();
  for (const item of items.filter((candidate) => candidate.track === "home")) {
    const presentation = reviewerHomeProductPresentation(item.merchant_sku_id);
    if (presentation) itemByPresentationId.set(presentation.id, item);
  }
  return products.map((product) => {
    const item = itemByPresentationId.get(product.id);
    if (item) return { ...product, itemId: item.item_id };
    // Presentation-only cards must not retain the old local-demo UUIDs.
    // That prevents a reviewer who signed in through Google from ever
    // attempting an action against another account's fixture workflow.
    const { itemId: _itemId, ...visual } = product;
    return visual;
  });
}

export function reviewerShowcaseSubscriptions(items: TrackedItem[]): SubscriptionProduct[] {
  const itemByPresentationId = new Map<string, TrackedItem>();
  for (const item of items.filter((candidate) => candidate.track === "teams")) {
    const presentation = reviewerTeamSubscriptionPresentation(item.merchant_sku_id);
    if (presentation) itemByPresentationId.set(presentation.id, item);
  }
  return subscriptions.map((subscription) => {
    const item = itemByPresentationId.get(subscription.id);
    if (item) return { ...subscription, itemId: item.item_id };
    const { itemId: _itemId, ...visual } = subscription;
    return visual;
  });
}

export function reviewerShowcaseNotifications(pending: Notification[]): Notification[] {
  const pendingTracks = new Set(pending.map((notification) => notification.track));
  return [
    ...pending,
    ...previews.filter((notification) => !pendingTracks.has(notification.track)),
  ];
}

export function notificationsForReviewerSession(
  pending: Notification[],
  showcaseRequested: boolean,
  reviewerFixture: boolean,
): Notification[] {
  return showcaseRequested || reviewerFixture
    ? reviewerShowcaseNotifications(pending)
    : pending;
}

const DAY_MS = 86_400_000;

function dateLabel(value?: string | null): string {
  if (!value) return "Not recorded";
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return "Not recorded";
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

function daysFromToday(value?: string | null): number | null {
  if (!value) return null;
  const target = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(target.getTime())) return null;
  const today = new Date();
  const todayUtc = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  return Math.ceil((target.getTime() - todayUtc) / DAY_MS);
}

function moneyLabel(value: string | null | undefined, currency: string): string {
  if (!value || !Number.isFinite(Number(value))) return "Quote pending";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: Number(value) % 1 === 0 ? 0 : 2,
  }).format(Number(value));
}

function trackedHomeProduct(base: PantryProduct, item: TrackedItem): PantryProduct {
  const providerResolved = Boolean(item.merchant_address_ref);
  const cadence = item.typical_cadence_days || 0;
  const lastPurchase = item.last_purchased_at ? new Date(`${item.last_purchased_at}T00:00:00Z`) : null;
  const predictedDate = lastPurchase && cadence
    ? new Date(lastPurchase.getTime() + cadence * DAY_MS).toISOString().slice(0, 10)
    : null;
  const remaining = daysFromToday(predictedDate);
  const price = providerResolved ? item.last_observed_price : null;
  const priceTriggered = Boolean(
    providerResolved
    && item.price_threshold
    && item.last_observed_price
    && Number(item.last_observed_price) <= Number(item.price_threshold),
  );
  const due = remaining !== null && remaining <= 3;
  const trigger = priceTriggered && due
    ? "Depletion and price threshold"
    : priceTriggered
      ? "Price threshold"
      : "Predicted depletion";
  const status = !providerResolved
    ? "Connect exact Zepto product"
    : remaining === null
    ? "Learning cadence"
    : remaining <= 0
      ? "Due now"
      : `${remaining} day${remaining === 1 ? "" : "s"} left`;
  const lifecycle: ProductLifecycle = providerResolved && (priceTriggered || due) ? "attention" : "tracking";
  return {
    ...base,
    itemId: item.item_id,
    name: item.name,
    merchant: item.preferred_merchant === "zepto" ? "Zepto" : item.preferred_merchant === "swiggy" ? "Swiggy" : base.merchant,
    category: item.category.replaceAll("_", " "),
    price: moneyLabel(price, item.currency),
    lastBought: dateLabel(item.last_purchased_at),
    cadence: cadence ? `every ${Number(cadence.toFixed(1))} days` : "Still learning",
    daysRemaining: !providerResolved ? "provider match required" : remaining === null ? "not enough history yet" : remaining <= 0 ? "due now" : `about ${remaining} days`,
    status,
    trigger: providerResolved ? trigger : "Live product match required",
    lifecycle,
    nextDue: !providerResolved ? "after live catalog matching" : remaining === null ? "after more purchase history" : status.toLowerCase(),
  };
}

function presentationProductForItem(item: TrackedItem): PantryProduct {
  const reviewerProduct = reviewerHomeProductPresentation(item.merchant_sku_id);
  if (reviewerProduct) {
    return {
      ...reviewerProduct,
      id: `tracked-${item.item_id}`,
      itemId: item.item_id,
    };
  }
  return {
    id: `tracked-${item.item_id}`,
    itemId: item.item_id,
    name: item.name,
    image: "/app/assets/restock-mark.png",
    imageAlt: "Restock tracked-product marker",
    brand: item.merchant_address_ref ? "Zepto catalog" : "Provider match needed",
    category: item.category.replaceAll("_", " "),
    size: item.quantity ? `Quantity ${item.quantity}` : "Exact SKU pending",
    tone: "watching",
    status: item.merchant_address_ref ? "Watching" : "Connect exact product",
    price: item.merchant_address_ref ? moneyLabel(item.last_observed_price, item.currency) : "Quote pending",
    merchant: "Zepto",
    lastBought: dateLabel(item.last_purchased_at),
    daysRemaining: item.merchant_address_ref ? "learning from real purchases" : "provider match required",
    cadence: item.typical_cadence_days ? `every ${Number(item.typical_cadence_days.toFixed(1))} days` : "Still learning",
    trigger: item.merchant_address_ref ? "Predicted depletion" : "Live product match required",
    ingredients: "Product details remain at Zepto",
    nutrition: item.merchant_address_ref
      ? "Restock stores the exact SKU, current observed price, quantity and saved-address reference—not invented catalog copy."
      : "This older item is retained for history but cannot trigger a purchase until it is matched to a live Zepto SKU and saved address.",
    lifecycle: "tracking",
    nextDue: item.merchant_address_ref ? "after purchase history establishes a clock" : "after live catalog matching",
  };
}

function trackedTeamSubscription(item: TrackedItem): SubscriptionProduct {
  const current = moneyLabel(item.current_plan_amount, item.currency);
  const alternate = moneyLabel(item.alternate_plan_amount, item.currency);
  const currentValue = Number(item.current_plan_amount || 0);
  const alternateValue = Number(item.alternate_plan_amount || 0);
  const savings = currentValue > alternateValue
    ? `${moneyLabel(String(currentValue - alternateValue), item.currency)} per renewal`
    : "No cheaper match";
  const renewalDays = daysFromToday(item.renewal_date);
  const decisionDue = renewalDays !== null && renewalDays <= 3;
  const reviewerSubscription = reviewerTeamSubscriptionPresentation(item.merchant_sku_id);
  return {
    ...(reviewerSubscription || {}),
    id: reviewerSubscription ? `tracked-${item.item_id}` : "tracked-team-subscription",
    itemId: item.item_id,
    name: item.name,
    category: "SaaS subscription",
    logo: reviewerSubscription?.logo || "/app/assets/restock-mark.png",
    color: reviewerSubscription?.color || "#17624d",
    currentPlan: reviewerSubscription?.currentPlan || "Tracked invoice",
    currentAmount: current,
    alternatePlan: item.alternate_plan_label || "Alternate plan",
    alternateAmount: alternate,
    renewal: dateLabel(item.renewal_date),
    cadence: "Renewal date supplied by owner",
    owner: "Billing owner not supplied",
    savings,
    status: decisionDue ? "Decision due" : "Watching",
    note: reviewerSubscription?.note || "The invoice date and amounts below are the values supplied to Restock. Vendor dashboard data is not inferred.",
    description: reviewerSubscription?.description || "A persisted team subscription loaded from the Restock production database.",
    currency: item.currency === "INR" ? "INR" : "USD",
    priceBasis: reviewerSubscription?.priceBasis || "owner-supplied hosted invoice",
    quantity: reviewerSubscription?.quantity || "Subscription object not connected by vendor OAuth",
    usage: reviewerSubscription?.usage || "Not supplied",
    usageDetail: reviewerSubscription?.usageDetail || "Restock does not invent seats or usage when a vendor billing API is not connected.",
    paymentMethod: "Prava approval required",
    invoiceStatus: decisionDue ? "Approval due" : "Not due",
    planFeatures: reviewerSubscription?.planFeatures || ["Hosted invoice reference", "Explicit renewal action", "Code-owned spend cap"],
    alternateDescription: `Move to ${item.alternate_plan_label || "the alternate plan"} only after a distinct switch approval.`,
  };
}

const revealAssets = [
  "/app/assets/cardboard-texture-cc0.png",
  "/app/assets/restock-mark-white.png",
  ...products.map((product) => product.image),
  ...subscriptions.flatMap((subscription) => {
    const slug = subscription.logo.split("/").pop()?.replace(/\.(svg|png)$/i, "") || "award-base";
    return [
      `/app/assets/3d/subscription-awards/${slug}.png`,
      `/app/assets/3d/subscription-awards/${slug}-mark.png`,
    ];
  }),
];

const actionLabels: Record<string, string> = {
  approve: "Approve",
  adjust: "Adjust",
  skip: "Skip",
  renew_as_is: "Renew as-is",
  switch_plan: "Switch plan",
};

type SubscriptionPlanChoice = {
  id: "current" | "alternate";
  name: string;
  amount: string;
  currency: SubscriptionProduct["currency"];
  cadence: string;
  description: string;
  features: string[];
  savings: string;
};

function planChoicesFor(subscription: SubscriptionProduct): SubscriptionPlanChoice[] {
  const current: SubscriptionPlanChoice = {
    id: "current",
    name: subscription.currentPlan,
    amount: subscription.currentAmount,
    currency: subscription.currency,
    cadence: subscription.cadence,
    description: subscription.description,
    features: subscription.planFeatures,
    savings: "Current billing arrangement",
  };
  if (["Keep current", "Usage review"].includes(subscription.alternatePlan)) return [current];
  return [
    current,
    {
      id: "alternate",
      name: subscription.alternatePlan,
      amount: subscription.alternateAmount,
      currency: subscription.currency,
      cadence: subscription.alternatePlan.toLowerCase().includes("annual") ? "Annual commitment" : subscription.cadence,
      description: subscription.alternateDescription,
      features: [
        "Separate plan-change approval",
        "Fresh vendor quote before payment",
        "Effective date shown in review",
      ],
      savings: subscription.savings,
    },
  ];
}

const humanize = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

let sharedAudioContext: AudioContext | null = null;

function playInterfaceSound(kind: SoundKind) {
  const AudioContextClass = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextClass) return;
  if (!sharedAudioContext) sharedAudioContext = new AudioContextClass();
  const context = sharedAudioContext;
  if (context.state === "suspended") void context.resume();

  const notes: Record<SoundKind, [number, number, number]> = {
    hover: [420, 465, 0.045],
    open: [285, 620, 0.16],
    close: [480, 300, 0.11],
    navigate: [370, 440, 0.075],
    submit: [330, 405, 0.085],
    confirm: [390, 680, 0.14],
  };
  const [start, end, duration] = notes[kind];
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  oscillator.type = kind === "confirm" ? "triangle" : "sine";
  oscillator.frequency.setValueAtTime(start, context.currentTime);
  oscillator.frequency.exponentialRampToValueAtTime(end, context.currentTime + duration);
  gain.gain.setValueAtTime(0.0001, context.currentTime);
  gain.gain.exponentialRampToValueAtTime(kind === "hover" ? 0.012 : 0.028, context.currentTime + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + duration);
  oscillator.connect(gain);
  gain.connect(context.destination);
  oscillator.start();
  oscillator.stop(context.currentTime + duration + 0.01);
}

function usePaperWind<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const lastPointer = useRef({ x: 0, y: 0, at: 0 });
  const frame = useRef<number | null>(null);

  useEffect(() => () => {
    if (frame.current !== null) window.cancelAnimationFrame(frame.current);
  }, []);

  const writeWind = (x: number, y: number, turn: number) => {
    const element = ref.current;
    if (!element) return;
    element.style.setProperty("--paper-wind-x", `${x.toFixed(2)}px`);
    element.style.setProperty("--paper-wind-y", `${y.toFixed(2)}px`);
    element.style.setProperty("--paper-wind-turn", `${turn.toFixed(2)}deg`);
  };

  const onPointerMove = (event: React.PointerEvent<T>) => {
    if (
      event.pointerType === "touch"
      || window.matchMedia("(prefers-reduced-motion: reduce)").matches
      || (event.target as HTMLElement).closest("button, input, a")
    ) return;
    const now = performance.now();
    const elapsed = Math.max(12, now - lastPointer.current.at);
    const velocityX = (event.clientX - lastPointer.current.x) / elapsed;
    const velocityY = (event.clientY - lastPointer.current.y) / elapsed;
    lastPointer.current = { x: event.clientX, y: event.clientY, at: now };
    const x = Math.max(-2.8, Math.min(2.8, velocityX * 8));
    const y = Math.max(-1.4, Math.min(1.4, velocityY * 5));
    const turn = Math.max(-0.8, Math.min(0.8, velocityX * 2.4));
    if (frame.current !== null) window.cancelAnimationFrame(frame.current);
    frame.current = window.requestAnimationFrame(() => writeWind(x, y, turn));
  };

  const onPointerLeave = () => {
    lastPointer.current = { x: 0, y: 0, at: 0 };
    if (frame.current !== null) window.cancelAnimationFrame(frame.current);
    frame.current = window.requestAnimationFrame(() => writeWind(0, 0, 0));
  };

  return { ref, onPointerMove, onPointerLeave };
}

function ModeBadge({ mode, label }: { mode: string; label?: string }) {
  return <span className="mode-badge">{label || humanize(mode)}</span>;
}

function Brand() {
  return (
    <span className="brand-lockup">
      <img src="/app/assets/restock-mark.png" alt="" className="brand-mark" />
      <span>restock.</span>
    </span>
  );
}

function AppHeader({
  view,
  setView,
  soundOn,
  setSoundOn,
  notifications,
  profile,
  tenant,
  capabilities,
  watchedCount,
  onOpenNotification,
  onGoogleLinked,
  onLogout,
}: {
  view: View;
  setView: (view: View) => void;
  soundOn: boolean;
  setSoundOn: (enabled: boolean) => void;
  notifications: Notification[];
  profile: UserProfile | null;
  tenant: TenantSummary | null;
  capabilities: Capabilities | null;
  watchedCount: number;
  onOpenNotification: (notification: Notification) => void;
  onGoogleLinked: (credential: string) => Promise<void>;
  onLogout: () => Promise<void>;
}) {
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileTriggerRef = useRef<HTMLButtonElement>(null);
  const navigation: { id: View; label: string; icon: typeof House }[] = [
    { id: "home", label: "Home", icon: House },
    { id: "teams", label: "Teams", icon: UsersThree },
    { id: "activity", label: "Activity", icon: ClockCounterClockwise },
  ];
  const displayName = profile?.display_name || "Soumyajit";
  const initials = displayName
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  const detectedTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "Local time";
  const localTimezone = detectedTimezone === "Asia/Calcutta" ? "Asia/Kolkata" : detectedTimezone;
  const capLabel = (value: string | number | undefined | null) => (
    value === undefined || value === null ? "—" : `₹${value}`
  );
  const googleLinked = profile?.auth_providers?.includes("google") ?? false;

  useEffect(() => {
    if (!profileOpen && !notificationsOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setProfileOpen(false);
      setNotificationsOpen(false);
      profileTriggerRef.current?.focus();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [notificationsOpen, profileOpen]);

  return (
    <header className="app-header">
      <button className="brand-button" type="button" onClick={() => setView("home")} aria-label="Open my pantry">
        <Brand />
        <span className="brand-context">my pantry</span>
      </button>

      <nav className="top-navigation" aria-label="Primary navigation">
        {navigation.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={view === id ? "top-nav-item top-nav-item--active" : "top-nav-item"}
            onClick={() => setView(id)}
            aria-current={view === id ? "page" : undefined}
          >
            <Icon size={17} weight={view === id ? "fill" : "regular"} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="header-tools">
        <button
          className="sound-toggle"
          type="button"
          aria-pressed={soundOn}
          aria-label={soundOn ? "Turn sound off" : "Turn sound on"}
          onClick={() => setSoundOn(!soundOn)}
        >
          {soundOn ? <SpeakerHigh size={18} weight="fill" /> : <SpeakerSlash size={18} />}
          <span>Sound {soundOn ? "on" : "off"}</span>
        </button>

        <button
          className="header-icon-button"
          type="button"
          aria-label={`${notifications.length} pending notifications`}
          aria-expanded={notificationsOpen}
          aria-controls="restock-notification-center"
          onClick={() => {
            setNotificationsOpen((open) => !open);
            setProfileOpen(false);
          }}
        >
          <BellSimpleRinging size={19} weight={notifications.length ? "fill" : "regular"} />
          {notifications.length > 0 && <span className="header-count">{notifications.length}</span>}
        </button>

        <button
          ref={profileTriggerRef}
          className="profile-trigger"
          type="button"
          aria-label={`Open ${displayName}'s profile`}
          aria-expanded={profileOpen}
          aria-controls="restock-profile-folio"
          onClick={() => {
            setProfileOpen((open) => !open);
            setNotificationsOpen(false);
          }}
        >
          <span className="profile-avatar">{initials || <UserCircle size={19} />}</span>
          <span className="profile-trigger-name">{displayName.split(" ")[0]}</span>
          <CaretDown size={13} />
        </button>
      </div>

      {notificationsOpen && (
        <section id="restock-notification-center" className="notification-center" aria-label="Pending decisions">
          <header>
            <span>
              <p className="eyebrow">Restock slips</p>
              <strong>{notifications.length ? "Needs your say" : "All quiet"}</strong>
            </span>
            <button type="button" aria-label="Close notifications" onClick={() => setNotificationsOpen(false)}>
              <X size={16} />
            </button>
          </header>
          <div className="notification-center-list">
            {notifications.length === 0 ? (
              <p className="notification-center-empty">Nothing needs attention right now.</p>
            ) : notifications.map((notification) => (
              <button
                key={notification.notification_id}
                type="button"
                className="notification-center-slip"
                onClick={() => {
                  setNotificationsOpen(false);
                  onOpenNotification(notification);
                }}
              >
                <span className="notification-track">{notification.track === "teams" ? "Teams" : "Home"}</span>
                <strong>{notification.message}</strong>
                <small>Open the tracked item <ArrowRight size={13} /></small>
              </button>
            ))}
          </div>
        </section>
      )}

      {profileOpen && (
        <div className="profile-scrim" onMouseDown={() => setProfileOpen(false)}>
          <aside
            id="restock-profile-folio"
            className="profile-folio"
            aria-label={`${displayName}'s Restock profile`}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="profile-folio-header">
              <div>
                <div className="profile-identity">
                  <span className="profile-avatar profile-avatar--large">{initials || <UserCircle size={24} />}</span>
                  <span>
                    <p className="eyebrow">My pantry folio</p>
                    <h2>{displayName}</h2>
                    <small>{tenant?.name || "Personal pantry"} · {tenant?.role || "Owner"}</small>
                  </span>
                </div>
                <p className="profile-summary">
                  <strong>{watchedCount} items watched</strong>
                  <span aria-hidden="true">·</span>
                  <strong>{notifications.length} decisions waiting</strong>
                </p>
              </div>
              <button
                type="button"
                aria-label="Close profile"
                onClick={() => {
                  setProfileOpen(false);
                  profileTriggerRef.current?.focus();
                }}
              >
                <X size={18} />
              </button>
            </header>

            <section className="profile-ledger-section">
              <header className="profile-section-heading">
                <span className="profile-section-icon"><UserCircle size={20} weight="duotone" /></span>
                <span>
                  <p>Identity</p>
                  <small>The person and pantry Restock is acting for.</small>
                </span>
              </header>
              <dl className="profile-ledger profile-ledger--identity">
                <div><dt>Pantry</dt><dd>{tenant?.name || "Personal pantry"}</dd></div>
                <div><dt>Role</dt><dd>{tenant?.role || "Owner"}</dd></div>
                <div><dt>Local time</dt><dd>{localTimezone}</dd></div>
              </dl>
            </section>

            <section className="profile-ledger-section">
              <header className="profile-section-heading">
                <span className="profile-section-icon"><CurrencyInr size={20} weight="duotone" /></span>
                <span>
                  <p>Spending boundaries</p>
                  <small>Hard limits checked in code before Prava is called.</small>
                </span>
              </header>
              <dl className="profile-ledger profile-ledger--money">
                <div className="profile-ledger-primary"><dt>Monthly household limit</dt><dd>{capLabel(profile?.monthly_cap)}</dd></div>
                <div><dt>Per item</dt><dd>{capLabel(profile?.per_item_cap)}</dd></div>
                <div><dt>Per purchase</dt><dd>{capLabel(profile?.per_transaction_cap)}</dd></div>
              </dl>
              {!profile && <p className="profile-section-note">Sign in to load account limits.</p>}
            </section>

            <section className="profile-ledger-section">
              <header className="profile-section-heading">
                <span className="profile-section-icon"><ChatCircleDots size={20} weight="duotone" /></span>
                <span>
                  <p>Delivery routes</p>
                  <small>Where Home and Teams decisions can reach you.</small>
                </span>
              </header>
              <div className="profile-route-list">
                <div className="profile-route-row">
                  <span className="profile-route-mark profile-route-mark--restock"><img src="/app/assets/restock-mark.png" alt="" /></span>
                  <span><strong>In-app</strong><small>Immediate decisions and quiet updates</small></span>
                  <em data-state="active">Active</em>
                </div>
                <div className="profile-route-row">
                  <span className="profile-route-mark"><WhatsappLogo size={22} weight="fill" /></span>
                  <span><strong>WhatsApp</strong><small>Home approvals and replenishment reminders</small></span>
                  <em data-state={capabilities?.whatsapp_configured ? "active" : "inactive"}>
                    {capabilities?.whatsapp_configured ? "Connected" : "Not configured"}
                  </em>
                </div>
                <div className="profile-route-row">
                  <span className="profile-route-mark"><SlackLogo size={22} weight="fill" /></span>
                  <span><strong>Slack</strong><small>Teams renewals and plan-switch decisions</small></span>
                  <em data-state={capabilities?.slack_configured ? "active" : "inactive"}>
                    {capabilities?.slack_configured ? "Connected" : "Not configured"}
                  </em>
                </div>
              </div>
            </section>

            <section className="profile-ledger-section">
              <header className="profile-section-heading">
                <span className="profile-section-icon"><GlobeHemisphereEast size={20} weight="duotone" /></span>
                <span>
                  <p>Experience</p>
                  <small>Comfort settings stay predictable across devices.</small>
                </span>
              </header>
              <div className="profile-preference-list">
                <button type="button" onClick={() => setSoundOn(!soundOn)} aria-pressed={soundOn}>
                  <span>{soundOn ? <SpeakerHigh size={19} weight="fill" /> : <SpeakerSlash size={19} />}</span>
                  <span><strong>Restock sound</strong><small>{soundOn ? "On" : "Off"}</small></span>
                  <em>{soundOn ? "Turn off" : "Turn on"}</em>
                </button>
                <div>
                  <span><GlobeHemisphereEast size={19} weight="duotone" /></span>
                  <span><strong>Motion</strong><small>Follows your device preference</small></span>
                  <em>System</em>
                </div>
              </div>
            </section>

            {["google", "hybrid"].includes(capabilities?.auth_mode || "") && (
              <section className="profile-ledger-section profile-security">
                <header className="profile-section-heading">
                  <span className="profile-section-icon"><LockKey size={20} weight="duotone" /></span>
                  <span>
                    <p>Sign-in security</p>
                    <small>{googleLinked ? "Google is connected to this Restock account." : "Add Google as an everyday way to return to this pantry."}</small>
                  </span>
                </header>
                <div className="profile-google-link">
                  {googleLinked ? (
                    <>
                      <strong>Google sign-in connected</strong>
                      <p>Your Google password is handled by Google and is never shared with Restock.</p>
                      <span className="profile-google-linked" role="status">
                        <ShieldCheck size={17} weight="fill" aria-hidden="true" />
                        Connected
                      </span>
                    </>
                  ) : (
                    <>
                      <strong>Link Google sign-in</strong>
                      <p>
                        Confirm your Google account while you are already signed in. Restock never links
                        accounts from a matching email address alone.
                      </p>
                      <GoogleSignIn
                        clientId={capabilities?.google_client_id || ""}
                        mode="link"
                        onCredential={onGoogleLinked}
                      />
                    </>
                  )}
                </div>
              </section>
            )}

            <section className="profile-ledger-section profile-privacy-note">
              <ShieldCheck size={22} weight="duotone" />
              <span>
                <strong>Your data stays useful, not exposed.</strong>
                <small>Raw payment credentials and approval links never appear here. Forecasting uses only the tracking data you allow.</small>
              </span>
              <button type="button" disabled title="Data export is available after sign-in">
                <DownloadSimple size={17} /> Export my data
              </button>
            </section>

            <button
              className="profile-signout"
              type="button"
              onClick={() => void onLogout()}
            >
              <SignOut size={18} aria-hidden="true" />
              Sign out
            </button>
          </aside>
        </div>
      )}
    </header>
  );
}

function ForegroundNotificationSlip({
  notification,
  brand,
  onOpen,
  onClose,
}: {
  notification: Notification;
  brand: ProviderBrand;
  onOpen: () => void;
  onClose: () => void;
}) {
  const paperWind = usePaperWind<HTMLElement>();
  const isTeams = notification.track === "teams" || notification.actions.includes("switch_plan");
  return (
    <aside
      ref={paperWind.ref}
      className="foreground-notification"
      aria-label="Restock notification"
      onPointerMove={paperWind.onPointerMove}
      onPointerLeave={paperWind.onPointerLeave}
    >
      <p className="sr-only" role="status" aria-live="polite">{notification.message}</p>
      <header style={{ "--provider-accent": brand.accent } as React.CSSProperties}>
        <span className={`notification-mark${brand.wide ? " notification-mark--wide" : ""}`}>
          <img src={brand.logo} alt={`${brand.name} logo`} />
        </span>
        <span>
          <small>{brand.name} · {isTeams ? "Teams" : "Home"}</small>
          <strong>{isTeams ? "A renewal is waiting" : "Your pantry noticed something"}</strong>
        </span>
        <button type="button" aria-label="Dismiss this popup" onClick={onClose}><X size={16} /></button>
      </header>
      <p className="foreground-message">{notification.message}</p>
      <footer>
        <button type="button" className="notification-later" onClick={onClose}>Later</button>
        <button type="button" className="notification-view" onClick={onOpen}>
          View {isTeams ? "renewal" : "item"} <ArrowRight size={15} />
        </button>
      </footer>
    </aside>
  );
}

function ProductOnShelf({
  product,
  onOpen,
  onPreview,
}: {
  product: PantryProduct;
  onOpen: () => void;
  onPreview: () => void;
}) {
  return (
    <button
      className={`shelf-product shelf-product--${product.id}`}
      type="button"
      onClick={onOpen}
      onPointerEnter={onPreview}
      aria-label={`Open ${product.name}: ${product.status}`}
      data-product-id={product.id}
      data-lifecycle={product.lifecycle}
    >
      <span className="product-wind-layer">
        <span className="product-float-layer">
          <span className="product-photo-wrap">
            <img src={product.image} alt={product.imageAlt} className="shelf-product-image" />
          </span>
        </span>
      </span>
      <span className="product-caption">
        <strong>{product.name}</strong>
        <span className="caption-commerce">
          <small>{product.size}</small>
          <span className="shelf-price-pin">{product.price}</span>
        </span>
        <span className="caption-status" data-tone={product.tone}>{product.status}</span>
      </span>
    </button>
  );
}

export function resolveProductLifecycle({
  base,
  itemId,
  workflows,
  hasPendingNotification,
}: {
  base: ProductLifecycle;
  itemId?: string;
  workflows: WorkflowRun[];
  hasPendingNotification: boolean;
}): ProductLifecycle {
  const terminalStates = new Set(["completed", "failed", "skipped", "rejected", "expired"]);
  const latest = itemId
    ? workflows
      .filter((workflow) => workflow.item_id === itemId)
      .sort((left, right) => String(right.updated_at || "").localeCompare(String(left.updated_at || "")))[0]
    : undefined;
  if (latest?.state === "completed") return "restocked";
  if (latest && !terminalStates.has(latest.state)) return "attention";
  if (latest && terminalStates.has(latest.state)) return "tracking";
  if (hasPendingNotification) return "attention";
  return base;
}

function LivingPantry({
  products: trackedProducts,
  onOpen,
  onPreview,
  onStartPantry,
  workflows,
  notification,
}: {
  products: PantryProduct[];
  onOpen: (product: PantryProduct) => void;
  onPreview: () => void;
  onStartPantry?: () => void;
  workflows: WorkflowRun[];
  notification?: Notification;
}) {
  const stageRef = useRef<HTMLElement>(null);
  const animationFrame = useRef<number | null>(null);
  const presentationProducts = useMemo(() => trackedProducts.map((product) => {
    const lifecycle = resolveProductLifecycle({
      base: product.lifecycle,
      itemId: product.itemId,
      workflows,
      hasPendingNotification: (notification?.item_id
        ? product.itemId === notification.item_id
        : product.id === "coffee")
        && Boolean(notification && ["pending", "preview"].includes(notification.status)),
    });
    return { ...product, lifecycle };
  }), [notification, trackedProducts, workflows]);
  const shelfProducts = presentationProducts.filter((product) => product.lifecycle !== "restocked");
  const upperProducts = shelfProducts.slice(0, 3);
  const middleProducts = shelfProducts.slice(3, 5);
  const lowerProducts = shelfProducts.slice(5, 8);

  const updateWind = (event: React.PointerEvent<HTMLElement>) => {
    if (
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
      || window.matchMedia("(pointer: coarse)").matches
      || window.innerWidth < 800
    ) return;

    const stage = stageRef.current;
    if (!stage) return;
    const bounds = stage.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 2;
    const y = ((event.clientY - bounds.top) / bounds.height - 0.5) * 2;
    if (animationFrame.current) window.cancelAnimationFrame(animationFrame.current);
    animationFrame.current = window.requestAnimationFrame(() => {
      stage.style.setProperty("--wind-x", `${(x * 5).toFixed(2)}px`);
      stage.style.setProperty("--wind-y", `${(y * 3).toFixed(2)}px`);
      stage.style.setProperty("--tag-turn", `${(x * 2.4).toFixed(2)}deg`);
      stage.style.setProperty("--sun-shift", `${(x * -5).toFixed(2)}px`);
      stage.style.setProperty("--product-tilt-x", `${(y * -1.4).toFixed(2)}deg`);
      stage.style.setProperty("--product-tilt-y", `${(x * 2.6).toFixed(2)}deg`);
    });
  };

  const resetWind = () => {
    const stage = stageRef.current;
    if (!stage) return;
    stage.style.setProperty("--wind-x", "0px");
    stage.style.setProperty("--wind-y", "0px");
    stage.style.setProperty("--tag-turn", "0deg");
    stage.style.setProperty("--sun-shift", "0px");
    stage.style.setProperty("--product-tilt-x", "0deg");
    stage.style.setProperty("--product-tilt-y", "0deg");
  };

  useEffect(() => () => {
    if (animationFrame.current) window.cancelAnimationFrame(animationFrame.current);
  }, []);

  return (
    <main className="pantry-page">
      <section
        ref={stageRef}
        className="pantry-stage"
        aria-label="Tracked household products on three shelves"
        onPointerMove={updateWind}
        onPointerLeave={resetWind}
      >
        <div className="sunlit-room" aria-hidden="true" />
        <div className="pantry-shelf-note">
          <span className="pantry-shelf-note__kicker">My pantry</span>
          <h1>Living pantry</h1>
        </div>
        <p className="ambient-copy" aria-hidden="true">watched with care</p>

        <div className="shelf-level shelf-level--upper">
          <div className="shelf-items shelf-items--upper">
            {upperProducts.map((product) => (
              <ProductOnShelf
                key={product.id}
                product={product}
                onOpen={() => onOpen(product)}
                onPreview={onPreview}
              />
            ))}
          </div>
          <div className="wood-shelf" aria-hidden="true" />
        </div>

        <div className="shelf-level shelf-level--middle">
          <div className="shelf-items shelf-items--middle">
            {middleProducts.map((product) => (
              <ProductOnShelf
                key={product.id}
                product={product}
                onOpen={() => onOpen(product)}
                onPreview={onPreview}
              />
            ))}
          </div>
          <div className="wood-shelf" aria-hidden="true" />
        </div>

        <div className="shelf-level shelf-level--lower">
          <div className="shelf-items shelf-items--lower">
            {lowerProducts.map((product) => (
              <ProductOnShelf
                key={product.id}
                product={product}
                onOpen={() => onOpen(product)}
                onPreview={onPreview}
              />
            ))}
          </div>
          <div className="wood-shelf" aria-hidden="true" />
        </div>

        {shelfProducts.length === 0 && (
          <div className="shelf-empty">
            <strong>Everything is stocked.</strong>
            <span>The next item will appear here when its trigger fires.</span>
            {onStartPantry && (
              <button type="button" className="shelf-empty__action" onClick={onStartPantry}>
                Add pantry items
              </button>
            )}
          </div>
        )}
      </section>
    </main>
  );
}

function AdjustAmount({
  initialAmount,
  onCancel,
  onSubmit,
}: {
  initialAmount: string;
  onCancel: () => void;
  onSubmit: (amount: string) => void;
}) {
  const [value, setValue] = useState(initialAmount);
  const valid = Number(value) > 0;
  return (
    <form
      className="adjust-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (valid) onSubmit(value);
      }}
    >
      <label htmlFor="adjust-amount">Set a new maximum amount</label>
      <div className="amount-field">
        <span aria-hidden="true">₹</span>
        <input id="adjust-amount" inputMode="decimal" value={value} onChange={(event) => setValue(event.target.value)} autoFocus />
      </div>
      <div className="adjust-actions">
        <button className="button button--secondary" type="button" onClick={onCancel}>Cancel</button>
        <button className="button button--primary" type="submit" disabled={!valid}>Save amount</button>
      </div>
    </form>
  );
}

function ProductDetail({
  product,
  notification,
  capabilities,
  busy,
  actionStatus,
  onBack,
  onAction,
}: {
  product: PantryProduct;
  notification?: Notification;
  capabilities: Capabilities | null;
  busy: boolean;
  actionStatus: string;
  onBack: () => void;
  onAction: (notification: Notification, action: string, adjustedAmount?: string) => void;
}) {
  const [adjusting, setAdjusting] = useState(false);
  const backButtonRef = useRef<HTMLButtonElement>(null);
  const adjustButtonRef = useRef<HTMLButtonElement>(null);
  const actionable = Boolean(notification && ["pending", "preview"].includes(notification.status));
  const isCoffee = product.id === "coffee";
  const isFood = ["Coffee", "Dairy", "Pantry"].includes(product.category);
  const merchantBrand = providerBrandForName(product.merchant);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onBack();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onBack]);

  useEffect(() => {
    backButtonRef.current?.focus({ preventScroll: true });
  }, [product.id]);

  return (
    <main className="product-detail">
      <button ref={backButtonRef} className="back-button" type="button" onClick={onBack}>
        <ArrowLeft size={18} />
        <span>Back to the pantry</span>
      </button>

      <ParcelReveal3D
        content={{
          kind: "product",
          image: product.image,
          name: product.name,
          scale: product.id === "oil"
            ? 0.96
            : product.id === "paper"
              ? 1.22
              : product.id === "toothpaste"
                ? 1.1
                : 1.1,
          bottom: product.id === "toothpaste"
            ? "52%"
            : product.id === "filter"
              ? "49%"
              : undefined,
        }}
        parcelLabel={`restock care parcel no. ${products.findIndex((item) => item.id === product.id) + 1}`}
        merchantLabel={product.merchant}
      />

      <div className="detail-story">
        <section className="detail-content">
          <div className="detail-title">
            <p className="eyebrow">{product.lifecycle === "attention" ? "On your shelf" : product.lifecycle === "restocked" ? "Cycle complete" : "Quietly tracking"} · {product.category}</p>
            <h1>{product.name}</h1>
            <div className="detail-commerce" aria-label={`Current price ${product.price}; source ${product.merchant}; product by ${product.brand}`}>
              <span className="price-pin"><Tag size={17} weight="fill" /><strong>{product.price}</strong></span>
              <span className="commerce-chip">
                {merchantBrand
                  ? <img className={`commerce-brand-logo${merchantBrand.wide ? " commerce-brand-logo--wide" : ""}`} src={merchantBrand.logo} alt={`${merchantBrand.name} logo`} />
                  : <Storefront size={18} weight="duotone" />}
                <span><small>Source merchant</small><strong>{product.merchant}</strong></span>
              </span>
              <span className="commerce-chip">
                <SealCheck size={18} weight="duotone" />
                <span><small>Product by</small><strong>{product.brand}</strong></span>
              </span>
              <span className="detail-status-pill"><Clock size={15} />{product.status}</span>
            </div>
          </div>

          {isCoffee && (
            <div className="trigger-callout">
              <BellSimpleRinging size={22} weight="fill" />
              <div>
                <strong>Two signals met at once</strong>
                <p>You’ll run out in about 2 days, and the price dropped below your ₹400 threshold.</p>
              </div>
            </div>
          )}

          {isCoffee && notification && (
            adjusting ? (
              <AdjustAmount
                initialAmount={product.price.replace(/[^\d.]/g, "") || "0"}
                onCancel={() => {
                  setAdjusting(false);
                  window.requestAnimationFrame(() => adjustButtonRef.current?.focus());
                }}
                onSubmit={(amount) => { setAdjusting(false); onAction(notification, "adjust", amount); }}
              />
            ) : (
              <>
                <p className="action-boundary">
                  {capabilities?.real_money_enabled && capabilities.home_payment_mode === "real"
                    ? `Live checkout · approving can create a real ${product.price} charge.`
                    : "Approval demonstration · no real merchant charge will be made."}
                </p>
                <div className="detail-actions" role="group" aria-label="Coffee restock actions" aria-busy={busy}>
                  {notification.actions.map((action) => (
                    <button
                      key={action}
                      ref={action === "adjust" ? adjustButtonRef : undefined}
                      type="button"
                      className={`button ${action === "approve" ? "button--primary" : action === "skip" ? "button--quiet-danger" : "button--secondary"}`}
                      onClick={() => action === "adjust" ? setAdjusting(true) : onAction(notification, action)}
                      disabled={!actionable || busy}
                    >
                      {busy ? "Working…" : action === "approve" ? `Approve ${product.price}` : actionLabels[action] || humanize(action)}
                    </button>
                  ))}
                </div>
              </>
            )
          )}
          <p className="detail-action-status" role="status" aria-live="polite">{actionStatus}</p>
          <p className="payment-note">
            <LockKey size={15} />
            Approval creates a scoped Prava mandate. Nothing continues until you confirm.
          </p>
        </section>

        <dl className="product-facts" aria-label={`${product.name} product snapshot`}>
          <div className="product-fact product-fact--history">
            <span className="fact-icon"><CalendarBlank size={23} weight="duotone" /></span>
            <span><dt>Last bought</dt><dd>{product.lastBought}</dd></span>
          </div>
          <div className="product-fact product-fact--cadence">
            <span className="fact-icon"><Timer size={23} weight="duotone" /></span>
            <span><dt>Expected to last</dt><dd>{product.cadence}</dd></span>
          </div>
          <div className="product-fact product-fact--remaining">
            <span className="fact-icon"><HourglassMedium size={23} weight="duotone" /></span>
            <span><dt>Estimated remaining</dt><dd>{product.daysRemaining}</dd></span>
          </div>
          <div className="product-fact product-fact--trigger">
            <span className="fact-icon"><BellSimpleRinging size={23} weight="duotone" /></span>
            <span><dt>Why Restock noticed</dt><dd>{product.trigger}</dd></span>
          </div>
          <div className="product-fact product-fact--ingredients">
            <span className="fact-icon">{isFood ? <ForkKnife size={23} weight="duotone" /> : <Package size={23} weight="duotone" />}</span>
            <span><dt>{isFood ? "Ingredients" : "Material / compatibility"}</dt><dd>{product.ingredients}</dd></span>
          </div>
          <div className="product-fact product-fact--note">
            <span className="fact-icon">{isFood ? <Sparkle size={23} weight="duotone" /> : <ListBullets size={23} weight="duotone" />}</span>
            <span><dt>{isFood ? "Label note" : "Product note"}</dt><dd>{product.nutrition}</dd></span>
          </div>
        </dl>
      </div>
    </main>
  );
}

function SubscriptionTicket({
  subscription,
  onOpen,
  onPreview,
}: {
  subscription: SubscriptionProduct;
  onOpen: () => void;
  onPreview: () => void;
}) {
  return (
    <button
      type="button"
      className="provider-award"
      onClick={onOpen}
      onPointerEnter={onPreview}
      data-subscription-id={subscription.id}
      aria-label={`Open ${subscription.name}: ${subscription.status}`}
    >
      <ProviderAward3D
        logo={subscription.logo}
        accent={subscription.color}
        name={subscription.name}
        live={subscription.status === "Decision due"}
      />
      <span className="award-plaque">
        <span className="award-plaque-title">{subscription.name}</span>
        <span className="award-meta">
          <small>{subscription.renewal}</small>
          <strong>{subscription.currentAmount}</strong>
        </span>
        <span className="award-status" data-status={subscription.status === "Decision due" ? "due" : "watching"}>
          {subscription.status === "Decision due" ? <Clock size={14} weight="fill" /> : <Eye size={14} weight="duotone" />}
          {subscription.status}
        </span>
      </span>
    </button>
  );
}

function TeamsGallery({
  subscriptions: trackedSubscriptions,
  onOpen,
  onPreview,
  onAdd,
}: {
  subscriptions: SubscriptionProduct[];
  onOpen: (subscription: SubscriptionProduct) => void;
  onPreview: () => void;
  onAdd: () => void;
}) {
  const stageRef = useRef<HTMLElement>(null);
  const animationFrame = useRef<number | null>(null);

  const updateWind = (event: React.PointerEvent<HTMLElement>) => {
    if (
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
      || window.matchMedia("(pointer: coarse)").matches
      || window.innerWidth < 800
    ) return;

    const stage = stageRef.current;
    if (!stage) return;
    const bounds = stage.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 2;
    const y = ((event.clientY - bounds.top) / bounds.height - 0.5) * 2;
    if (animationFrame.current) window.cancelAnimationFrame(animationFrame.current);
    animationFrame.current = window.requestAnimationFrame(() => {
      stage.style.setProperty("--wind-x", `${(x * 4).toFixed(2)}px`);
      stage.style.setProperty("--wind-y", `${(y * 2).toFixed(2)}px`);
      stage.style.setProperty("--tag-turn", `${(x * 2).toFixed(2)}deg`);
      stage.style.setProperty("--award-tilt-x", `${(y * -1.1).toFixed(2)}deg`);
      stage.style.setProperty("--award-tilt-y", `${(x * 2.2).toFixed(2)}deg`);
      stage.style.setProperty("--cabinet-light-x", `${(x * -5).toFixed(2)}px`);
      stage.style.setProperty("--cabinet-light-y", `${(y * -2).toFixed(2)}px`);
    });
  };

  const resetWind = () => {
    const stage = stageRef.current;
    if (!stage) return;
    stage.style.setProperty("--wind-x", "0px");
    stage.style.setProperty("--wind-y", "0px");
    stage.style.setProperty("--tag-turn", "0deg");
    stage.style.setProperty("--award-tilt-x", "0deg");
    stage.style.setProperty("--award-tilt-y", "0deg");
    stage.style.setProperty("--cabinet-light-x", "0px");
    stage.style.setProperty("--cabinet-light-y", "0px");
  };

  useEffect(() => () => {
    if (animationFrame.current) window.cancelAnimationFrame(animationFrame.current);
  }, []);

  return (
    <main className="teams-page">
      <section
        ref={stageRef}
        className="subscription-cabinet"
        aria-label="Tracked team subscriptions"
        onPointerMove={updateWind}
        onPointerLeave={resetWind}
      >
        <div className="cabinet-light" aria-hidden="true" />
        <div className="teams-shelf-note">
          <span>Restock Teams</span>
          <h1>Subscription shelf</h1>
        </div>
        <button className="teams-add-subscription" type="button" onClick={onAdd}>
          <Receipt size={18} weight="duotone" />
          Track an invoice
        </button>
        <div className="award-shelf award-shelf--upper">
          <div className="award-items">
            {trackedSubscriptions.slice(0, 3).map((subscription) => (
              <SubscriptionTicket
                key={subscription.id}
                subscription={subscription}
                onOpen={() => onOpen(subscription)}
                onPreview={onPreview}
              />
            ))}
          </div>
          <div className="wood-shelf" aria-hidden="true" />
        </div>
        <div className="award-shelf award-shelf--lower">
          <div className="award-items">
            {trackedSubscriptions.slice(3).map((subscription) => (
              <SubscriptionTicket
                key={subscription.id}
                subscription={subscription}
                onOpen={() => onOpen(subscription)}
                onPreview={onPreview}
              />
            ))}
          </div>
          <div className="wood-shelf" aria-hidden="true" />
        </div>
      </section>
    </main>
  );
}

function TeamsSubscriptionSetup({
  onBack,
  onComplete,
}: {
  onBack: () => void;
  onComplete: (input: {
    vendor_name: string;
    invoice_id: string;
    hosted_payment_reference: string;
    currency: string;
    renewal_date: string;
    current_plan_amount: string;
  }) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [values, setValues] = useState({
    vendor_name: "",
    invoice_id: "",
    hosted_payment_reference: "",
    currency: "USD",
    renewal_date: "",
    current_plan_amount: "",
  });
  const update = (key: keyof typeof values, value: string) => {
    setValues((current) => ({ ...current, [key]: value }));
  };
  return (
    <main className="teams-setup">
      <button className="back-button" type="button" onClick={onBack}>
        <ArrowLeft size={18} />
        <span>Back to renewals</span>
      </button>
      <section className="teams-setup-receipt" aria-labelledby="teams-setup-title">
        <header>
          <span className="receipt-provider-mark"><Receipt size={26} weight="duotone" /></span>
          <p className="eyebrow">Hosted invoice only</p>
          <h1 id="teams-setup-title">Track a subscription</h1>
          <p>Paste the vendor’s payable invoice link. Restock never asks for, stores, or automates the vendor account password.</p>
        </header>
        <form onSubmit={(event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          void onComplete(values)
            .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not track this subscription."))
            .finally(() => setBusy(false));
        }}>
          <label><span>Vendor</span><input required maxLength={200} value={values.vendor_name} onChange={(event) => update("vendor_name", event.target.value)} placeholder="GitHub, Figma, Vercel…" /></label>
          <label><span>Invoice reference</span><input required maxLength={255} value={values.invoice_id} onChange={(event) => update("invoice_id", event.target.value)} placeholder="INV-2026-08" /></label>
          <label className="teams-setup-wide"><span>Hosted invoice reference</span><input required pattern="[A-Za-z0-9._:-]+" value={values.hosted_payment_reference} onChange={(event) => update("hosted_payment_reference", event.target.value)} placeholder="github-aug-2026" /></label>
          <label><span>Renewal date</span><input required type="date" value={values.renewal_date} onChange={(event) => update("renewal_date", event.target.value)} /></label>
          <label><span>Amount</span><input required type="number" min="0.01" step="0.01" value={values.current_plan_amount} onChange={(event) => update("current_plan_amount", event.target.value)} placeholder="29.00" /></label>
          <label><span>Currency</span><input required minLength={3} maxLength={3} value={values.currency} onChange={(event) => update("currency", event.target.value.toUpperCase())} /></label>
          {error && <p className="login-error teams-setup-wide" role="alert">{error}</p>}
          <footer className="teams-setup-wide">
            <p><LockKey size={16} /> The payment link stays in server secret management. A changed amount stops for a new approval.</p>
            <button className="button button--teams" type="submit" disabled={busy}>{busy ? "Adding…" : "Track this invoice"}</button>
          </footer>
        </form>
      </section>
    </main>
  );
}

function SubscriptionDetail({
  subscription,
  notification,
  capabilities,
  busy,
  actionStatus,
  onBack,
  onAction,
}: {
  subscription: SubscriptionProduct;
  notification?: Notification;
  capabilities: Capabilities | null;
  busy: boolean;
  actionStatus: string;
  onBack: () => void;
  onAction: (notification: Notification, action: string) => void;
}) {
  const backButtonRef = useRef<HTMLButtonElement>(null);
  const paperWind = usePaperWind<HTMLElement>();
  const actionable = subscription.id === "copilot" && Boolean(notification && ["pending", "preview"].includes(notification.status));
  const choices = useMemo(() => planChoicesFor(subscription), [subscription]);
  const [activePanel, setActivePanel] = useState<"receipt" | "plans" | "invoices">("receipt");
  const [selectedChoiceId, setSelectedChoiceId] = useState<SubscriptionPlanChoice["id"]>("current");
  const [reviewing, setReviewing] = useState(false);
  const selectedChoice = choices.find((choice) => choice.id === selectedChoiceId) || choices[0];
  const selectedAction = selectedChoice.id === "alternate" ? "switch_plan" : "renew_as_is";
  const canSubmitSelected = Boolean(
    actionable
    && notification
    && notification.actions.includes(selectedAction),
  );

  useEffect(() => {
    setActivePanel("receipt");
    setSelectedChoiceId("current");
    setReviewing(false);
    backButtonRef.current?.focus({ preventScroll: true });
  }, [subscription.id]);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (reviewing) {
        setReviewing(false);
        return;
      }
      onBack();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onBack, reviewing]);

  const openPlans = (choice: SubscriptionPlanChoice["id"] = "current") => {
    setSelectedChoiceId(choice);
    setReviewing(false);
    setActivePanel("plans");
  };

  const confirmSelectedPlan = () => {
    if (!notification || !canSubmitSelected) return;
    onAction(notification, selectedAction);
  };

  return (
    <main
      className="subscription-detail"
      style={{ "--provider-accent": subscription.color } as CSSProperties}
    >
      <button ref={backButtonRef} className="back-button" type="button" onClick={onBack}>
        <ArrowLeft size={18} />
        <span>Back to renewals</span>
      </button>

      <ParcelReveal3D
        content={{
          kind: "award",
          logo: subscription.logo,
          name: subscription.name,
          accent: subscription.color,
          scale: 1.08,
        }}
        parcelLabel={`${subscription.category} · renewal packet`}
        merchantLabel={subscription.name}
      />

      <div className="billing-receipt-stage">
        <span className="receipt-shadow-sheet" aria-hidden="true" />
        <article
          ref={paperWind.ref}
          className="billing-receipt"
          aria-label={`${subscription.name} billing receipt`}
          onPointerMove={paperWind.onPointerMove}
          onPointerLeave={paperWind.onPointerLeave}
        >
          <div className="receipt-feed-edge" aria-hidden="true" />
          <header className="receipt-heading">
            <div className="receipt-brand">
              <img className="receipt-restock-mark" src="/app/assets/restock-mark.png" alt="" />
              <span>
                <small>Restock billing statement</small>
                <strong>Subscription receipt</strong>
              </span>
            </div>
            <span className={`receipt-status-stamp${subscription.status === "Decision due" ? " receipt-status-stamp--due" : ""}`}>
              {subscription.status}
            </span>
          </header>

          <div className="receipt-provider">
            <span className="receipt-provider-mark"><img src={subscription.logo} alt="" /></span>
            <span>
              <p className="receipt-kicker">{subscription.owner} · {subscription.category}</p>
              <h2>{subscription.name}</h2>
              <p>{subscription.description}</p>
            </span>
            <span className="receipt-total">
              <small>Recurring total</small>
              <strong>{subscription.currentAmount}</strong>
              <em>{subscription.currency} · {subscription.priceBasis}</em>
            </span>
          </div>

          <nav className="receipt-tabs" aria-label="Billing receipt sections">
            {(["receipt", "plans", "invoices"] as const).map((panel) => (
              <button
                key={panel}
                type="button"
                className={activePanel === panel ? "receipt-tab receipt-tab--active" : "receipt-tab"}
                aria-current={activePanel === panel ? "page" : undefined}
                onClick={() => {
                  setActivePanel(panel);
                  setReviewing(false);
                }}
              >
                {panel === "receipt" ? "Receipt" : panel === "plans" ? "Plans" : "Invoices"}
              </button>
            ))}
          </nav>

          {activePanel === "receipt" && (
            <section className="receipt-section" aria-labelledby="current-plan-heading">
              <div className="receipt-section-title">
                <span><Receipt size={20} weight="duotone" /></span>
                <p>
                  <small>Your plan now</small>
                  <strong id="current-plan-heading">{subscription.currentPlan}</strong>
                </p>
                <em><Check size={13} weight="bold" /> Current</em>
              </div>

              <dl className="receipt-ledger">
                <div><dt>Billing owner</dt><span aria-hidden="true" /><dd>{subscription.owner}</dd></div>
                <div><dt>Quantity</dt><span aria-hidden="true" /><dd>{subscription.quantity}</dd></div>
                <div><dt>Billing cadence</dt><span aria-hidden="true" /><dd>{subscription.cadence}</dd></div>
                <div><dt>Next renewal</dt><span aria-hidden="true" /><dd>{subscription.renewal}</dd></div>
                <div className="receipt-ledger-total"><dt>Expected total</dt><span aria-hidden="true" /><dd>{subscription.currentAmount} {subscription.currency}</dd></div>
              </dl>

              <div className="receipt-perforation" aria-hidden="true"><span>Plan includes</span></div>
              <div className="receipt-feature-list">
                {subscription.planFeatures.map((feature, index) => (
                  <div key={feature}>
                    <span>{index === 0 ? <Lightning size={18} weight="duotone" /> : index === 1 ? <ShieldCheck size={18} weight="duotone" /> : <Gauge size={18} weight="duotone" />}</span>
                    <strong>{feature}</strong>
                  </div>
                ))}
              </div>

              <div className="receipt-usage-line">
                <Gauge size={20} weight="duotone" />
                <span><strong>{subscription.usage}</strong><small>{subscription.usageDetail}</small></span>
              </div>
            </section>
          )}

          {activePanel === "plans" && (
            <section className="receipt-section receipt-section--plans" aria-labelledby="compare-plans-heading">
              <div className="receipt-section-title">
                <span><ArrowsClockwise size={20} weight="duotone" /></span>
                <p>
                  <small>Pull-out plan slips</small>
                  <strong id="compare-plans-heading">{choices.length > 1 ? "Compare your options" : "Your current plan"}</strong>
                </p>
              </div>
              <p className="receipt-intro">Choosing a slip prepares a review. It never changes or pays for a plan by itself.</p>

              <fieldset className="receipt-plan-slips">
                <legend className="sr-only">Choose a subscription plan to review</legend>
                {choices.map((choice, index) => {
                  const selected = selectedChoice.id === choice.id;
                  return (
                    <label
                      key={choice.id}
                      className={selected ? "receipt-plan-slip receipt-plan-slip--selected" : "receipt-plan-slip"}
                      style={{ "--slip-index": index } as CSSProperties}
                    >
                      <input
                        type="radio"
                        name={`${subscription.id}-plan`}
                        value={choice.id}
                        checked={selected}
                        onChange={() => {
                          setSelectedChoiceId(choice.id);
                          setReviewing(false);
                        }}
                      />
                      <span className="receipt-plan-radio"><Check size={13} weight="bold" /></span>
                      <span className="receipt-plan-copy">
                        <span>
                          <strong>{choice.name}</strong>
                          {choice.id === "current" && <small>Current plan</small>}
                        </span>
                        <em>{choice.description}</em>
                        {selected && choice.features.map((feature) => (
                          <small key={feature}><CheckCircle size={14} weight="fill" /> {feature}</small>
                        ))}
                      </span>
                      <span className="receipt-plan-price">
                        <strong>{choice.amount}</strong>
                        <small>{choice.currency}</small>
                        <em>{choice.savings}</em>
                      </span>
                    </label>
                  );
                })}
              </fieldset>

              {!reviewing ? (
                <div className="receipt-review-prompt">
                  <p>
                    {selectedChoice.id === "alternate"
                      ? "A plan switch always needs its own explicit approval."
                      : "Review the renewal amount before approving it as-is."}
                  </p>
                  <button type="button" className="button button--teams" onClick={() => setReviewing(true)} disabled={busy}>
                    <span>Review {selectedChoice.id === "alternate" ? "switch" : "renewal"}</span>
                    <CaretRight className="button-progress-icon" size={16} weight="bold" aria-hidden="true" />
                  </button>
                </div>
              ) : (
                <section className="receipt-tearoff" aria-labelledby="plan-review-title">
                  <p className="receipt-tearoff-label">Tear-off approval slip</p>
                  <h3 id="plan-review-title">{selectedChoice.id === "alternate" ? "Plan switch" : "Renewal"} review</h3>
                  <div className="receipt-route">
                    <span><small>From</small><strong>{subscription.currentPlan}</strong></span>
                    <ArrowRight size={18} />
                    <span><small>To</small><strong>{selectedChoice.name}</strong></span>
                  </div>
                  <dl className="receipt-ledger receipt-ledger--review">
                    <div><dt>Approve now</dt><span aria-hidden="true" /><dd>{selectedChoice.amount} {selectedChoice.currency}</dd></div>
                    <div><dt>Effective date</dt><span aria-hidden="true" /><dd>Shown in fresh vendor quote</dd></div>
                    <div><dt>Proration / tax</dt><span aria-hidden="true" /><dd>Shown before payment</dd></div>
                    <div><dt>Payment</dt><span aria-hidden="true" /><dd>{subscription.paymentMethod}</dd></div>
                  </dl>
                  <div className="receipt-review-actions" aria-busy={busy}>
                    <button type="button" className="button button--secondary" onClick={() => setReviewing(false)} disabled={busy}>Back</button>
                    <button type="button" className="button button--teams" onClick={confirmSelectedPlan} disabled={!canSubmitSelected || busy}>
                      {busy ? "Working…" : selectedChoice.id === "alternate" ? `Approve switch · ${selectedChoice.amount}` : `Approve renewal · ${selectedChoice.amount}`}
                    </button>
                  </div>
                  {!canSubmitSelected && (
                    <p className="receipt-unavailable">
                      {actionable ? "This action is not in the current approval request." : "Nothing is due today; this remains a read-only plan review."}
                    </p>
                  )}
                </section>
              )}
            </section>
          )}

          {activePanel === "invoices" && (
            <section className="receipt-section receipt-section--invoice" aria-labelledby="invoice-heading">
              <div className="receipt-section-title">
                <span><FileText size={20} weight="duotone" /></span>
                <p>
                  <small>Vendor paperwork</small>
                  <strong id="invoice-heading">Next billing event</strong>
                </p>
              </div>
              <div className="invoice-docket">
                <span className="invoice-docket-state">{subscription.invoiceStatus}</span>
                <strong>{subscription.currentAmount} {subscription.currency}</strong>
                <p>{subscription.currentPlan} · expected {subscription.renewal}</p>
                <dl className="receipt-ledger">
                  <div><dt>Payment boundary</dt><span aria-hidden="true" /><dd>{subscription.paymentMethod}</dd></div>
                  <div><dt>Invoice number</dt><span aria-hidden="true" /><dd>Loaded when sourced</dd></div>
                  <div><dt>Vendor receipt</dt><span aria-hidden="true" /><dd>Available after completion</dd></div>
                </dl>
              </div>
              <p className="invoice-empty-note">No sourced vendor invoice is loaded yet. Restock will not invent line items, tax, or proration.</p>
            </section>
          )}

          <footer className="receipt-footer">
            <div className="receipt-boundary">
              <SealCheck size={18} weight="duotone" />
              <span>
                <strong>Selection, approval, and payment stay separate.</strong>
                <small>{capabilities?.teams_real_money_enabled && capabilities.teams_billing_mode === "real" ? "Live hosted-invoice billing is enabled." : "This environment will not create a real vendor charge."}</small>
              </span>
            </div>
            <div className="receipt-footer-actions">
              {activePanel !== "plans" && (
                <button type="button" className="button button--teams" onClick={() => openPlans("current")}>
                  {choices.length > 1
                    ? <ArrowsClockwise size={18} weight="duotone" aria-hidden="true" />
                    : <Receipt size={18} weight="duotone" aria-hidden="true" />}
                  <span>{choices.length > 1 ? "Compare plans" : "View plan details"}</span>
                </button>
              )}
              {activePanel !== "invoices" && (
                <button type="button" className="button button--secondary" onClick={() => setActivePanel("invoices")}>
                  <FileText size={18} weight="duotone" aria-hidden="true" />
                  <span>View invoice</span>
                </button>
              )}
              {notification?.actions.includes("skip") && (
                <button type="button" className="button button--quiet-danger" onClick={() => onAction(notification, "skip")} disabled={!actionable || busy}>
                  Skip renewal
                </button>
              )}
            </div>
            <p className="receipt-note">{subscription.note}</p>
            <p className="receipt-explicit">“Switch plan” is always a separate decision. Renewing can never select the alternate.</p>
            <p className="detail-action-status" role="status" aria-live="polite">{actionStatus}</p>
          </footer>
          <div className="receipt-torn-edge" aria-hidden="true" />
        </article>
      </div>
    </main>
  );
}

function ActivityView({
  products: trackedProducts,
  audit,
  capabilities,
  workflows,
}: {
  products: PantryProduct[];
  audit: AuditEntry[];
  capabilities: Capabilities | null;
  workflows: WorkflowRun[];
}) {
  const completedProducts = trackedProducts.filter((product) => resolveProductLifecycle({
    base: product.lifecycle,
    itemId: product.itemId,
    workflows,
    hasPendingNotification: false,
  }) === "restocked");
  const currentStreak = completedProducts.length > 0 ? 7 : 0;
  const streakDays = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setHours(12, 0, 0, 0);
    date.setDate(date.getDate() - (6 - index));
    return {
      date,
      complete: index >= 7 - currentStreak,
      today: index === 6,
    };
  });

  return (
    <main className="activity-page">
      <div className="activity-heading">
        <p className="eyebrow">Your replenishment rhythm</p>
        <h1>A steady pantry,<br />one day at a time.</h1>
        <p>Every check means nothing due was forgotten that day.</p>
      </div>

      <section className="restock-streaks" aria-labelledby="restock-streak-title">
        <header className="streak-scoreboard">
          <div className="streak-total">
            <span className="streak-symbol" aria-hidden="true"><Fire size={28} weight="fill" /></span>
            <span>
              <strong>{currentStreak}</strong>
              <small>day streak</small>
            </span>
          </div>
          <div className="streak-summary">
            <p className="eyebrow">Pantry coverage streak</p>
            <h2 id="restock-streak-title">
              {currentStreak > 0 ? "Seven quiet wins in a row." : "Your first streak starts here."}
            </h2>
            <dl className="streak-stats">
              <div><dt>Longest</dt><dd>{currentStreak} days</dd></div>
              <div><dt>Cycles completed</dt><dd>{completedProducts.length}</dd></div>
              <div><dt>Items watched</dt><dd>{trackedProducts.length}</dd></div>
            </dl>
          </div>
        </header>

        {currentStreak === 0 ? (
          <div className="streak-empty">
            <CalendarBlank size={24} weight="duotone" />
            <span>
              <strong>No covered days yet</strong>
              <small>The first day completes after Restock handles every due item.</small>
            </span>
          </div>
        ) : (
          <>
            <ol className="streak-week" aria-label={`${currentStreak} consecutive covered days`}>
              {streakDays.map((day, index) => (
                <li
                  className={`streak-day${day.complete ? " streak-day--complete" : ""}${day.today ? " streak-day--today" : ""}`}
                  key={day.date.toISOString()}
                  style={{ "--streak-delay": `${index * 65}ms` } as CSSProperties}
                >
                  <time dateTime={day.date.toISOString().slice(0, 10)}>
                    <small>{day.date.toLocaleDateString(undefined, { weekday: "short" })}</small>
                    <span className="streak-day-check" aria-hidden="true">
                      {day.complete ? <Check size={22} weight="bold" /> : day.date.getDate()}
                    </span>
                    <strong>{day.today ? "Today" : day.date.toLocaleDateString(undefined, { day: "numeric", month: "short" })}</strong>
                  </time>
                </li>
              ))}
            </ol>

            <p className="streak-definition">
              <ShieldCheck size={18} weight="duotone" aria-hidden="true" />
              A day counts when every due item is restocked or consciously skipped—never when Restock acts without approval.
            </p>

            <section className="streak-badges" aria-labelledby="streak-badges-title">
              <header>
                <div>
                  <p className="eyebrow">Achievements</p>
                  <h3 id="streak-badges-title">Your pantry badges</h3>
                </div>
                <span>3 earned</span>
              </header>
              <div className="streak-badge-row">
                <article className="streak-badge streak-badge--gold">
                  <span className="streak-badge-medal"><Fire size={26} weight="fill" aria-hidden="true" /></span>
                  <strong>Seven steady days</strong>
                  <small>Earned today</small>
                </article>
                <article className="streak-badge streak-badge--amber">
                  <span className="streak-badge-medal"><Package size={26} weight="duotone" aria-hidden="true" /></span>
                  <strong>First cycle</strong>
                  <small>One refill completed</small>
                </article>
                <article className="streak-badge streak-badge--green">
                  <span className="streak-badge-medal"><Eye size={26} weight="duotone" aria-hidden="true" /></span>
                  <strong>Watchful pantry</strong>
                  <small>Seven items covered</small>
                </article>
                <article className="streak-badge streak-badge--locked">
                  <span className="streak-badge-medal"><LockKey size={23} weight="duotone" aria-hidden="true" /></span>
                  <strong>Fourteen-day rhythm</strong>
                  <small>7 days to go</small>
                </article>
              </div>
            </section>

            <div className="streak-milestones" aria-label="Completed replenishment milestones">
              <div className="streak-milestones-heading">
                <span><CheckCircle size={18} weight="fill" aria-hidden="true" /></span>
                <div>
                  <p className="eyebrow">Recent wins</p>
                  <strong>{completedProducts.length} completed {completedProducts.length === 1 ? "cycle" : "cycles"}</strong>
                </div>
              </div>
              {completedProducts.map((product) => (
                <article className="streak-milestone" key={product.id}>
                  <span className="streak-product-image"><img src={product.image} alt="" /></span>
                  <span>
                    <strong>{product.name}</strong>
                    <small>Restocked · next expected {product.nextDue}</small>
                  </span>
                  <span className="streak-milestone-cadence">
                    <ArrowsClockwise size={16} weight="duotone" aria-hidden="true" />
                    {product.cadence}
                  </span>
                </article>
              ))}
            </div>
          </>
        )}
      </section>

      <details className="environment-disclosure">
        <summary>How this environment works</summary>
        <div>
          <span>Prava</span><strong>{humanize(capabilities?.prava_mode || "unavailable")}</strong>
          <span>Home catalog</span><strong>{humanize(capabilities?.home_merchant_mode || "unavailable")}</strong>
          <span>Home payment</span><strong>{humanize(capabilities?.home_payment_mode || "unavailable")}</strong>
          <span>Teams billing</span><strong>{humanize(capabilities?.teams_billing_mode || "unavailable")}</strong>
        </div>
      </details>

      <section className="activity-list" aria-label="Audit history">
        {audit.length === 0 ? (
          <div className="activity-empty">
            <Receipt size={26} />
            <strong>No live activity yet</strong>
            <p>The first trigger, decision, and payment boundary will appear here.</p>
          </div>
        ) : audit.map((entry) => (
          <article className="activity-entry" key={entry.audit_id}>
            <span className="activity-icon"><CheckCircle size={18} weight="fill" /></span>
            <div><strong>{humanize(entry.event_type)}</strong><small>{new Date(entry.created_at).toLocaleString()}</small></div>
            <ModeBadge mode={Object.values(entry.modes)[0] || "sandbox"} />
          </article>
        ))}
      </section>
    </main>
  );
}

type RestockAuthMode = "solo" | "google" | "hybrid";

function configuredAuthMode(): RestockAuthMode {
  const configured = String(import.meta.env.VITE_RESTOCK_AUTH_MODE || "google");
  return configured === "solo" || configured === "hybrid" ? configured : "google";
}

export function LoginScreen({
  onGoogleLogin,
  onPasswordLogin,
  authMode = configuredAuthMode(),
  googleClientId = String(import.meta.env.VITE_GOOGLE_CLIENT_ID || ""),
  reviewerAccess = false,
}: {
  onGoogleLogin: (credential: string) => Promise<void>;
  onPasswordLogin?: (password: string) => Promise<void>;
  authMode?: RestockAuthMode;
  googleClientId?: string;
  reviewerAccess?: boolean;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!onPasswordLogin) return;
    setBusy(true);
    setError("");
    try {
      await onPasswordLogin(password);
      setPassword("");
    } catch {
      setPassword("");
      setError("Access was not accepted. Check the password and try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login-shell">
      <div className="login-scene">
        <aside className="login-parcel-stage" aria-hidden="true">
          <span className="login-stage-kicker">Packed quietly for you</span>
          <img
            className="login-parcel"
            src="/app/assets/3d/restock-parcel-closed-branded.png"
            alt=""
          />
          <div className="login-parcel-label">
            <img src="/app/assets/restock-mark.png" alt="" />
            <span>
              <small>Restock care parcel</small>
              <strong>Pantry & renewals</strong>
            </span>
          </div>
          <p>One calm place for what is running low and what is coming due.</p>
        </aside>

        <section className="login-card" aria-labelledby="login-title">
          <Brand />
          <div className="login-paper-copy">
            <p className="eyebrow">Your private Restock</p>
            <h1 id="login-title">Your pantry is waiting.</h1>
            <p className="login-copy">
              Continue to your tracked essentials, upcoming restocks, and renewal decisions.
            </p>
          </div>

          {authMode !== "solo" && (
            <>
              <GoogleSignIn clientId={googleClientId} onCredential={onGoogleLogin} />
              <p className="login-security">
                <ShieldCheck size={18} weight="duotone" aria-hidden="true" />
                <span>Restock never sees or stores your Google password.</span>
              </p>
            </>
          )}

          {authMode === "solo" && onPasswordLogin && (
            <form className="login-password-primary" onSubmit={(event) => void submit(event)}>
              <label htmlFor="solo-password">Password</label>
              <input
                id="solo-password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                maxLength={1024}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <p className="login-error" role="alert" aria-live="assertive">{error}</p>
              <button className="login-submit" type="submit" disabled={busy || !password}>
                {busy ? "Signing in…" : "Sign in"}
              </button>
            </form>
          )}

          {authMode === "hybrid" && onPasswordLogin && (
            <details className="login-recovery">
              <summary>{reviewerAccess ? "Prava reviewer access" : "Owner recovery access"}</summary>
              <form onSubmit={(event) => void submit(event)}>
                <label htmlFor="solo-password">{reviewerAccess ? "Reviewer password" : "Recovery password"}</label>
                {reviewerAccess && (
                  <p className="login-recovery__hint">This opens a pre-seeded review pantry; it is not a sign-up flow.</p>
                )}
                <input
                  id="solo-password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  maxLength={1024}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <p className="login-error" role="alert" aria-live="assertive">{error}</p>
                <button className="login-submit" type="submit" disabled={busy || !password}>
                  {busy ? "Checking access…" : reviewerAccess ? "Open reviewer pantry" : "Use recovery access"}
                </button>
              </form>
            </details>
          )}

          <footer className="login-legal">
            <span>By continuing, you agree to Restock’s</span>
            <a href="/app/terms.html">Terms</a>
            <span aria-hidden="true">·</span>
            <a href="/app/privacy.html">Privacy</a>
          </footer>
        </section>
      </div>
    </main>
  );
}

function AuthCheckingScreen() {
  return (
    <main className="login-shell" aria-busy="true">
      <section className="login-card login-card--checking">
        <Brand />
        <p className="login-copy">Opening your pantry…</p>
      </section>
    </main>
  );
}

function StarterPantryOnboarding({
  displayName,
  onComplete,
  onSkip,
}: {
  displayName: string;
  onComplete: (item: TrackedItem) => Promise<void>;
  onSkip: () => void;
}) {
  const [addresses, setAddresses] = useState<MerchantAddress[]>([]);
  const [addressRef, setAddressRef] = useState("");
  const [query, setQuery] = useState("coffee");
  const [products, setProducts] = useState<MerchantCatalogProduct[]>([]);
  const [selected, setSelected] = useState<MerchantCatalogProduct | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setBusy(true);
    void api.zeptoAddresses()
      .then(({ addresses: next }) => {
        if (!active) return;
        setAddresses(next);
        setAddressRef(next[0]?.reference || "");
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not connect to Zepto.");
      })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, []);

  const runSearch = async () => {
    if (!addressRef || query.trim().length < 2) return;
    setBusy(true);
    setError("");
    setSelected(null);
    try {
      const result = await api.zeptoProducts(query.trim(), addressRef);
      setProducts(result.products);
      if (!result.products.length) setError("No current Zepto products matched that search.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not search Zepto.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="starter-onboarding">
      <section className="starter-onboarding__paper" aria-labelledby="starter-title">
        <Brand />
        <div className="starter-onboarding__copy">
          <p className="eyebrow">Welcome, {displayName.split(" ")[0]}</p>
          <h1 id="starter-title">What should Restock watch first?</h1>
          <p>Choose an exact product from your connected Zepto account. Stock, SKU and price come from Zepto now—not from a Restock sample.</p>
        </div>

        <div className="starter-live-controls">
          <label>
            <span>Saved delivery address</span>
            <select value={addressRef} onChange={(event) => setAddressRef(event.target.value)} disabled={busy || !addresses.length}>
              {addresses.map((address) => <option key={address.reference} value={address.reference}>{address.label}</option>)}
            </select>
          </label>
          <form onSubmit={(event) => { event.preventDefault(); void runSearch(); }}>
            <label>
              <span>Find a pantry product</span>
              <input value={query} onChange={(event) => setQuery(event.target.value)} minLength={2} maxLength={120} placeholder="Coffee, milk, toothpaste…" />
            </label>
            <button type="submit" className="starter-submit" disabled={busy || !addressRef || query.trim().length < 2}>
              {busy ? "Checking Zepto…" : "Search live catalog"}
            </button>
          </form>
        </div>

        <fieldset className="starter-grid" hidden={!products.length}>
          <legend className="sr-only">Choose a live Zepto product</legend>
          {products.map((option) => {
            const checked = selected?.merchant_sku_id === option.merchant_sku_id;
            return (
              <label className="starter-item" data-selected={checked} key={option.merchant_sku_id}>
                <input
                  type="radio"
                  name="zepto-product"
                  checked={checked}
                  disabled={option.stock_status !== "in_stock"}
                  onChange={() => setSelected(option)}
                />
                <span className="starter-item__image"><Storefront size={34} weight="duotone" /></span>
                <span className="starter-item__copy">
                  <strong>{option.name}</strong>
                  <small>{moneyLabel(option.amount, option.currency)} · {option.stock_status === "in_stock" ? `${option.available_quantity} available` : "Out of stock"}</small>
                </span>
                <span className="starter-item__check" aria-hidden="true"><Check size={15} weight="bold" /></span>
              </label>
            );
          })}
        </fieldset>

        <p className="starter-onboarding__note">Only the provider’s opaque address and exact SKU are stored. Your street address remains with Zepto.</p>
        {error && <p className="login-error" role="alert">{error}</p>}
        <footer className="starter-onboarding__actions">
          <button type="button" className="starter-skip" onClick={onSkip} disabled={busy}>Start empty</button>
          <button
            type="button"
            className="starter-submit"
            disabled={busy || !selected || !addressRef}
            onClick={() => {
              if (!selected) return;
              setBusy(true);
              setError("");
              void api.createHomeCatalogItem({
                query,
                merchant_sku_id: selected.merchant_sku_id,
                merchant_address_ref: addressRef,
                category: "grocery",
                quantity: 1,
              }).then(onComplete)
                .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not set up your pantry."))
                .finally(() => setBusy(false));
            }}
          >
            {busy ? "Adding product…" : "Watch this product"}
            <ArrowRight size={17} />
          </button>
        </footer>
      </section>
    </main>
  );
}

export default function App() {
  const reviewerShowcaseRequested = reviewerShowcaseFromUrl();
  const [view, setView] = useState<View>(initialViewFromUrl);
  const [selectedProduct, setSelectedProduct] = useState<PantryProduct | null>(null);
  const [selectedSubscription, setSelectedSubscription] = useState<SubscriptionProduct | null>(null);
  const [notifications, setNotifications] = useState<Notification[]>(
    reviewerShowcaseRequested || import.meta.env.DEV ? previews : [],
  );
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowRun[]>([]);
  const [trackedItems, setTrackedItems] = useState<TrackedItem[]>([]);
  const [backendConnected, setBackendConnected] = useState(false);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [tenants, setTenants] = useState<TenantSummary[]>([]);
  const [foregroundNotification, setForegroundNotification] = useState<Notification | null>(null);
  const [status, setStatus] = useState("Ready");
  const [actionFeedback, setActionFeedback] = useState("");
  const [busyNotificationId, setBusyNotificationId] = useState<string | null>(null);
  const busyNotificationRef = useRef<string | null>(null);
  const lastProductId = useRef<string | null>(null);
  const lastSubscriptionId = useRef<string | null>(null);
  const [soundOn, setSoundOnState] = useState(() => window.localStorage.getItem("restock-sound") === "on");
  const [authState, setAuthState] = useState<"checking" | "required" | "ready">(
    import.meta.env.DEV ? "ready" : "checking",
  );
  const [onboardingDismissed, setOnboardingDismissed] = useState(false);
  const [teamsSetupOpen, setTeamsSetupOpen] = useState(false);

  useEffect(() => {
    const images = revealAssets.map((src) => {
      const image = new Image();
      image.decoding = "async";
      image.src = src;
      return image;
    });
    void Promise.allSettled(images.map((image) => image.decode()));
  }, []);

  const refresh = async () => {
    try {
      const caps = await api.capabilities();
      setCapabilities(caps);
      const [pending, events, workflowRuns, currentItems, currentUser, currentTenants] = await Promise.all([
        api.notifications(),
        api.audit(),
        api.workflows(),
        api.items(),
        api.me().catch(() => null),
        api.tenants().catch(() => []),
      ]);
      const visibleNotifications = notificationsForReviewerSession(
        pending,
        reviewerShowcaseRequested,
        Boolean(currentUser?.reviewer_fixture),
      );
      setNotifications(visibleNotifications);
      setAudit(events);
      setWorkflows(workflowRuns);
      setTrackedItems(currentItems);
      setBackendConnected(true);
      if (currentUser) setProfile(currentUser);
      setTenants(currentTenants);
      setAuthState("ready");
      setStatus(visibleNotifications.length ? `${visibleNotifications.length} decision${visibleNotifications.length === 1 ? "" : "s"} waiting` : "Everything is being watched");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        await clearApiSessionToken();
        setAuthState("required");
        setStatus("Sign in required");
        return;
      }
      setBackendConnected(false);
      if (import.meta.env.PROD) {
        setNotifications(reviewerShowcaseRequested ? previews : []);
        setTrackedItems([]);
      }
      setAuthState("ready");
      setStatus(import.meta.env.DEV ? "Local preview ready" : "Service temporarily unavailable");
    }
  };

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    let cleanupNative: () => void = () => {};
    void initializeNative(async (runId) => {
      setStatus("Approval returned · Resuming workflow");
      await api.resume(runId);
      await refresh();
    }).then((cleanup) => { cleanupNative = cleanup; });
    return () => {
      window.clearInterval(timer);
      cleanupNative();
    };
  }, []);

  const homeNotification = useMemo(
    () => notifications.find((notification) => (notification.track || (notification.actions.includes("switch_plan") ? "teams" : "home")) === "home"),
    [notifications],
  );
  const teamsNotification = useMemo(
    () => notifications.find((notification) => (notification.track || (notification.actions.includes("switch_plan") ? "teams" : "home")) === "teams"),
    [notifications],
  );
  // This is an explicit presentation route for provider review. It contains
  // only local, non-actionable visual fixtures; the default authenticated
  // view continues to show a user's own persisted products.
  const showReviewerShowcase = Boolean(profile?.reviewer_fixture) || reviewerShowcaseRequested;
  const visibleProducts = useMemo(() => {
    if (!backendConnected) return import.meta.env.DEV ? products : [];
    if (showReviewerShowcase) return reviewerShowcaseProducts(trackedItems);
    return trackedItems
      .filter((item) => item.track === "home")
      .map((item) => trackedHomeProduct(presentationProductForItem(item), item));
  }, [backendConnected, showReviewerShowcase, trackedItems]);
  const visibleSubscriptions = useMemo(() => {
    if (!backendConnected) return import.meta.env.DEV ? subscriptions : [];
    if (showReviewerShowcase) return reviewerShowcaseSubscriptions(trackedItems);
    const tracked = trackedItems.filter((item) => item.track === "teams");
    return tracked.map((item) => trackedTeamSubscription(item));
  }, [backendConnected, showReviewerShowcase, trackedItems]);

  useEffect(() => {
    if (selectedProduct || selectedSubscription || foregroundNotification) return;
    const candidate = notifications.find((notification) => ["pending", "preview"].includes(notification.status));
    if (!candidate) return;
    const presentationKey = `restock-notification-shown:${candidate.notification_id}:${candidate.status}`;
    if (window.sessionStorage.getItem(presentationKey)) return;
    const timer = window.setTimeout(() => {
      window.sessionStorage.setItem(presentationKey, "true");
      setForegroundNotification(candidate);
    }, 900);
    return () => window.clearTimeout(timer);
  }, [foregroundNotification, notifications, selectedProduct, selectedSubscription]);

  if (authState === "checking") return <AuthCheckingScreen />;

  if (authState === "required") {
    const finishSignIn = async () => {
      setAuthState("checking");
      await refresh();
    };
    return (
      <LoginScreen
        authMode={
          capabilities?.auth_mode === "solo" || capabilities?.auth_mode === "hybrid"
            ? capabilities.auth_mode
            : "google"
        }
        googleClientId={capabilities?.google_client_id || ""}
        reviewerAccess={Boolean(capabilities?.reviewer_access_configured)}
        onGoogleLogin={async (credential) => {
          await api.googleLogin(credential);
          await finishSignIn();
        }}
        onPasswordLogin={["solo", "hybrid"].includes(capabilities?.auth_mode || "") ? async (password) => {
          await api.login(password);
          await finishSignIn();
        } : undefined}
      />
    );
  }

  if (
    backendConnected
    && profile
    && trackedItems.length === 0
    && !onboardingDismissed
  ) {
    return (
      <StarterPantryOnboarding
        displayName={profile.display_name}
        onSkip={() => setOnboardingDismissed(true)}
        onComplete={async (item) => {
          setTrackedItems((current) => [...current, item]);
          setOnboardingDismissed(true);
          setStatus(`${item.name} is now being watched`);
        }}
      />
    );
  }

  const sound = (kind: SoundKind) => {
    if (soundOn) playInterfaceSound(kind);
  };

  const setSoundOn = (enabled: boolean) => {
    setSoundOnState(enabled);
    window.localStorage.setItem("restock-sound", enabled ? "on" : "off");
    if (enabled) playInterfaceSound("confirm");
  };

  const setViewWithSound = (nextView: View) => {
    sound("navigate");
    setSelectedProduct(null);
    setSelectedSubscription(null);
    setTeamsSetupOpen(false);
    setActionFeedback("");
    setView(nextView);
    const url = new URL(window.location.href);
    url.searchParams.set("view", nextView);
    window.history.replaceState({}, "", url);
  };

  const openProduct = (product: PantryProduct) => {
    lastProductId.current = product.id;
    setActionFeedback("");
    sound("open");
    setSelectedProduct(product);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" }));
  };

  const closeProduct = () => {
    sound("close");
    setSelectedProduct(null);
    window.requestAnimationFrame(() => {
      if (!lastProductId.current) return;
      document.querySelector<HTMLButtonElement>(`[data-product-id="${lastProductId.current}"]`)?.focus();
    });
  };

  const openSubscription = (subscription: SubscriptionProduct) => {
    lastSubscriptionId.current = subscription.id;
    setActionFeedback("");
    sound("open");
    setSelectedSubscription(subscription);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" }));
  };

  const openNotification = (notification: Notification) => {
    setForegroundNotification(null);
    const isTeams = notification.track === "teams" || notification.actions.includes("switch_plan");
    if (isTeams) {
      setViewWithSound("teams");
      const subscription = visibleSubscriptions[0];
      if (subscription) openSubscription(subscription);
      return;
    }
    setViewWithSound("home");
    const product = visibleProducts.find((candidate) => candidate.id === "coffee") || visibleProducts[0];
    if (product) openProduct(product);
  };

  const providerBrandForNotification = (notification: Notification): ProviderBrand => {
    const isTeams = notification.track === "teams" || notification.actions.includes("switch_plan");
    if (isTeams) {
      const subscription = visibleSubscriptions.find((candidate) => candidate.itemId === notification.item_id)
        || visibleSubscriptions.find((candidate) => candidate.id === "copilot")
        || visibleSubscriptions[0];
      return providerBrandForName(subscription?.name || "GitHub") || {
        name: "Restock Teams",
        logo: "/app/assets/restock-mark.png",
        accent: "#1f6b54",
      };
    }
    const product = visibleProducts.find((candidate) => candidate.itemId === notification.item_id)
      || visibleProducts.find((candidate) => candidate.id === "coffee")
      || visibleProducts[0];
    return providerBrandForName(product?.merchant || "Zepto") || {
      name: product?.merchant || "Restock Home",
      logo: "/app/assets/restock-mark.png",
      accent: "#1f6b54",
    };
  };

  const renderApprovalHandoff = (target: Window, brand: ProviderBrand) => {
    const document = target.document;
    document.title = `${brand.name} · secure approval`;
    document.documentElement.lang = "en";
    document.body.replaceChildren();
    Object.assign(document.body.style, {
      margin: "0",
      minHeight: "100vh",
      display: "grid",
      placeItems: "center",
      background: "#f4f4ef",
      color: "#161714",
      fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
    });
    const card = document.createElement("main");
    Object.assign(card.style, {
      width: "min(420px, calc(100vw - 40px))",
      padding: "42px 36px",
      border: "1px solid #deded5",
      borderTop: `5px solid ${brand.accent}`,
      borderRadius: "24px",
      background: "#fffefa",
      boxShadow: "0 28px 80px rgba(35, 37, 31, .14)",
      textAlign: "center",
      boxSizing: "border-box",
    });
    const logo = document.createElement("img");
    logo.src = new URL(brand.logo, window.location.origin).href;
    logo.alt = `${brand.name} logo`;
    Object.assign(logo.style, {
      display: "block",
      width: brand.wide ? "112px" : "64px",
      height: "64px",
      objectFit: "contain",
      margin: "0 auto 26px",
    });
    const eyebrow = document.createElement("p");
    eyebrow.textContent = `${brand.name} purchase`;
    Object.assign(eyebrow.style, {
      margin: "0 0 12px",
      color: brand.accent,
      fontSize: "12px",
      fontWeight: "700",
      letterSpacing: ".12em",
      textTransform: "uppercase",
    });
    const heading = document.createElement("h1");
    heading.textContent = "Opening secure approval";
    Object.assign(heading.style, { margin: "0", fontSize: "29px", letterSpacing: "-.04em" });
    const copy = document.createElement("p");
    copy.textContent = "You’ll continue on Prava’s protected payment surface. Keep this window open.";
    Object.assign(copy.style, { margin: "16px auto 0", maxWidth: "330px", color: "#6a6c65", lineHeight: "1.55" });
    const progress = document.createElement("div");
    progress.setAttribute("role", "progressbar");
    progress.setAttribute("aria-label", "Opening secure approval");
    Object.assign(progress.style, {
      width: "100%",
      height: "4px",
      marginTop: "30px",
      borderRadius: "999px",
      background: `linear-gradient(90deg, ${brand.accent} 58%, #e7e7df 58%)`,
    });
    card.append(logo, eyebrow, heading, copy, progress);
    document.body.append(card);
  };

  const closeSubscription = () => {
    sound("close");
    setSelectedSubscription(null);
    window.requestAnimationFrame(() => {
      if (!lastSubscriptionId.current) return;
      document.querySelector<HTMLButtonElement>(`[data-subscription-id="${lastSubscriptionId.current}"]`)?.focus();
    });
  };

  const act = async (notification: Notification, action: string, adjustedAmount?: string) => {
    if (busyNotificationRef.current) return;
    busyNotificationRef.current = notification.notification_id;
    setBusyNotificationId(notification.notification_id);
    sound("submit");
    let approvalWindow: Window | null = null;
    try {
      if (notification.status === "preview") {
        setNotifications((items) => items.map((item) => item.notification_id === notification.notification_id ? { ...item, status: action } : item));
        setStatus(`${humanize(action)} recorded`);
        setActionFeedback(`${humanize(action)} recorded. Restock will not take another action without a new decision.`);
        sound("confirm");
        return;
      }
      if (["approve", "renew_as_is", "switch_plan"].includes(action)) {
        approvalWindow = window.open("about:blank", "_blank");
        if (approvalWindow) {
          approvalWindow.opener = null;
          renderApprovalHandoff(approvalWindow, providerBrandForNotification(notification));
        }
      }
      const run = await api.action(notification.run_id, action, adjustedAmount);
      if (run.state === "passkey_pending") {
        const { approval_url } = await api.approvalUrl(notification.run_id);
        if (approvalWindow) approvalWindow.location.replace(approval_url);
        else window.location.assign(approval_url);
        setStatus("Passkey opened · Return after approval");
        setActionFeedback("Passkey approval opened in a new tab. Return here after approving.");
      } else {
        approvalWindow?.close();
        setStatus(`Workflow · ${humanize(run.state)}`);
        setActionFeedback(`Workflow updated: ${humanize(run.state)}.`);
      }
      sound("confirm");
      await refresh();
    } catch (error) {
      approvalWindow?.close();
      if (error instanceof ApiError && error.status === 401) {
        await clearApiSessionToken();
        setAuthState("required");
        setStatus("Sign in required");
        setActionFeedback("Your session expired. Sign in again to continue.");
        return;
      }
      const message = error instanceof Error ? error.message : "Action failed";
      setStatus(message);
      setActionFeedback(message);
    } finally {
      busyNotificationRef.current = null;
      setBusyNotificationId(null);
    }
  };

  return (
    <div className="app-shell">
      <AppHeader
        view={view}
        setView={setViewWithSound}
        soundOn={soundOn}
        setSoundOn={setSoundOn}
        notifications={notifications.filter((notification) => ["pending", "preview"].includes(notification.status))}
        profile={profile}
        tenant={tenants[0] || null}
        capabilities={capabilities}
        watchedCount={visibleProducts.filter((product) => product.lifecycle !== "restocked").length + visibleSubscriptions.length}
        onOpenNotification={openNotification}
        onGoogleLinked={async (credential) => {
          await api.googleLink(credential);
          const currentUser = await api.me();
          setProfile(currentUser);
        }}
        onLogout={async () => {
          try {
            await api.logout();
          } finally {
            setProfile(null);
            setTenants([]);
            setTrackedItems([]);
            setNotifications([]);
            setBackendConnected(false);
            setAuthState("required");
            setStatus("Signed out");
          }
        }}
      />
      <p className="sr-only" role="status" aria-live="polite">{status}</p>
      {foregroundNotification && !selectedProduct && !selectedSubscription && (
        <ForegroundNotificationSlip
          notification={foregroundNotification}
          brand={providerBrandForNotification(foregroundNotification)}
          onClose={() => setForegroundNotification(null)}
          onOpen={() => openNotification(foregroundNotification)}
        />
      )}
      {selectedProduct && view === "home" ? (
        <ProductDetail
          product={selectedProduct}
          notification={
            selectedProduct.itemId === homeNotification?.item_id
            || (!homeNotification?.item_id && selectedProduct.id === "coffee")
              ? homeNotification
              : undefined
          }
          capabilities={capabilities}
          busy={busyNotificationId === homeNotification?.notification_id}
          actionStatus={actionFeedback}
          onBack={closeProduct}
          onAction={(notification, action, amount) => void act(notification, action, amount)}
        />
      ) : view === "home" ? (
        <LivingPantry
          products={visibleProducts}
          onOpen={openProduct}
          onPreview={() => sound("hover")}
          onStartPantry={() => setOnboardingDismissed(false)}
          workflows={workflows}
          notification={homeNotification}
        />
      ) : selectedSubscription && view === "teams" ? (
        <SubscriptionDetail
          subscription={selectedSubscription}
          notification={
            selectedSubscription.itemId === teamsNotification?.item_id
            || (!teamsNotification?.item_id && selectedSubscription.id === "copilot")
              ? teamsNotification
              : undefined
          }
          capabilities={capabilities}
          busy={busyNotificationId === teamsNotification?.notification_id}
          actionStatus={actionFeedback}
          onBack={closeSubscription}
          onAction={(notification, action) => void act(notification, action)}
        />
      ) : teamsSetupOpen && view === "teams" ? (
        <TeamsSubscriptionSetup
          onBack={() => setTeamsSetupOpen(false)}
          onComplete={async (input) => {
            await api.createTeamsSubscription(input);
            await refresh();
            setTeamsSetupOpen(false);
            setStatus(`${input.vendor_name} is now tracked`);
          }}
        />
      ) : view === "teams" ? (
        <TeamsGallery subscriptions={visibleSubscriptions} onOpen={openSubscription} onPreview={() => sound("hover")} onAdd={() => setTeamsSetupOpen(true)} />
      ) : (
        <ActivityView products={visibleProducts} audit={audit} capabilities={capabilities} workflows={workflows} />
      )}
    </div>
  );
}
