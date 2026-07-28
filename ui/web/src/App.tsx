import { useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  CaretDown,
  CaretUp,
  Check,
  CheckCircle,
  Clock,
  ClockCounterClockwise,
  House,
  Info,
  LockKey,
  Package,
  Receipt,
  ShieldCheck,
  UsersThree,
  WarningCircle,
} from "@phosphor-icons/react";
import { ApiError, api, clearApiSessionToken, type AuditEntry, type Capabilities, type Notification } from "./api";
import { initializeNative } from "./native";

type Track = "home" | "teams";
type View = Track | "activity";

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
    message: "TeamTool Pro renews in 2 days. Renew for $29 or explicitly switch to the $24 annual plan?",
    actions: ["renew_as_is", "switch_plan", "skip"],
    status: "preview",
  },
];

const labels: Record<string, string> = {
  approve: "Approve ₹380",
  adjust: "Adjust",
  skip: "Skip",
  renew_as_is: "Renew as-is",
  switch_plan: "Switch plan",
};

const humanize = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

function ModeBadge({ mode, label }: { mode: string; label?: string }) {
  const isSimulated = mode.includes("mock") || mode.includes("unconfigured") || mode.includes("sandbox");
  return (
    <span className={`mode-badge ${isSimulated ? "mode-badge--sandbox" : "mode-badge--real"}`}>
      {isSimulated ? <ShieldCheck size={16} weight="regular" /> : <CheckCircle size={16} weight="fill" />}
      <span>{label || humanize(mode)}</span>
    </span>
  );
}

function AppHeader({ capabilities }: { capabilities: Capabilities | null }) {
  const mode = capabilities?.prava_mode || "sandbox_unconfigured";
  const paymentMode = capabilities?.home_payment_mode || "disclosed_mock";
  return (
    <header className="app-header">
      <a className="brand-lockup" href="#decisions" aria-label="Restock home">
        <img src="/app/assets/restock-mark.png" alt="" className="brand-mark" />
        <span>Restock</span>
      </a>
      <div className="header-context">
        <ModeBadge mode={mode} label={mode.includes("sandbox") ? "Sandbox" : undefined} />
        <span className="header-mode-copy">{paymentMode === "real" ? "Live merchant payment" : "Final payment simulated"}</span>
        <button className="profile-button" type="button" aria-label="Open account menu">
          <span className="profile-avatar" aria-hidden="true">SG</span>
          <span className="profile-name">Soumyajit</span>
          <CaretDown size={15} />
        </button>
      </div>
    </header>
  );
}

function Sidebar({ view, setView, capabilities }: { view: View; setView: (view: View) => void; capabilities: Capabilities | null }) {
  const navItems: { id: View; label: string; icon: typeof House }[] = [
    { id: "home", label: "Home", icon: House },
    { id: "teams", label: "Teams", icon: UsersThree },
    { id: "activity", label: "Activity", icon: ClockCounterClockwise },
  ];
  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <nav className="sidebar-nav">
        {navItems.map(({ id, label, icon: Icon }) => (
          <button
            className={`nav-item ${view === id ? "nav-item--active" : ""}`}
            key={id}
            type="button"
            onClick={() => setView(id)}
            aria-current={view === id ? "page" : undefined}
          >
            <Icon size={21} weight={view === id ? "fill" : "regular"} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-mode">
        <ModeBadge mode={capabilities?.home_merchant_mode || "disclosed_mock"} label={`Catalog · ${humanize(capabilities?.home_merchant_mode || "disclosed_mock")}`} />
        <ModeBadge mode={capabilities?.home_payment_mode || "disclosed_mock"} label={`Payment · ${humanize(capabilities?.home_payment_mode || "disclosed_mock")}`} />
        <p>Catalog data and final payment are disclosed independently.</p>
      </div>
    </aside>
  );
}

function DecisionHeader({ track, status }: { track: Track; status: string }) {
  return (
    <div className="page-heading" id="decisions">
      <div>
        <p className="section-kicker">{track === "home" ? "Household restocks" : "Team renewals"}</p>
        <h1>Decisions</h1>
        <p>Review and act before Restock places anything.</p>
      </div>
      <div className="sync-status" role="status" aria-live="polite">
        <span className="sync-dot" aria-hidden="true" />
        <span>{status}</span>
      </div>
    </div>
  );
}

function AdjustAmount({ onCancel, onSubmit }: { onCancel: () => void; onSubmit: (amount: string) => void }) {
  const [value, setValue] = useState("380");
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

function HomeDecision({
  notification,
  onAction,
  capabilities,
}: {
  notification: Notification;
  onAction: (notification: Notification, action: string, adjustedAmount?: string) => void;
  capabilities: Capabilities | null;
}) {
  const [expanded, setExpanded] = useState(true);
  const [adjusting, setAdjusting] = useState(false);
  const actionable = notification.status === "pending" || notification.status === "preview";
  return (
    <article className="decision decision--active">
      <header className="decision-summary">
        <img src="/app/assets/coffee-pouch.png" alt="Navy coffee pouch" className="product-image" />
        <div className="decision-title-block">
          <div className="reason-row">
            <span className="attention-label"><WarningCircle size={15} weight="fill" /> Action needed</span>
            <span className="reason-copy">Likely to run out in 2 days</span>
          </div>
          <h2>Arabica coffee beans · 500 g</h2>
          <div className="price-line">
            <strong>₹380</strong>
            <span>from Zepto</span>
            <span className="price-signal"><ArrowDown size={15} weight="bold" /> ₹20 below your alert threshold</span>
          </div>
          <ModeBadge
            mode={capabilities?.home_payment_mode || "disclosed_mock"}
            label={`${humanize(capabilities?.home_merchant_mode || "disclosed_mock")} catalog · ${humanize(capabilities?.home_payment_mode || "disclosed_mock")} payment`}
          />
        </div>
        <div className="decision-time">
          <span>Today</span>
          <small>10:24 AM</small>
          <button type="button" className="icon-button" aria-label={expanded ? "Collapse coffee details" : "Expand coffee details"} onClick={() => setExpanded((value) => !value)}>
            {expanded ? <CaretUp size={18} /> : <CaretDown size={18} />}
          </button>
        </div>
      </header>

      {expanded && (
        <>
          <dl className="decision-facts">
            <div><dt>Category</dt><dd>Groceries · Coffee</dd></div>
            <div><dt>Coverage</dt><dd>~2 days</dd></div>
            <div><dt>Merchant</dt><dd>Zepto</dd></div>
            <div><dt>Alert threshold</dt><dd>₹400.00</dd></div>
            <div><dt>Quantity</dt><dd>1 pouch</dd></div>
            <div><dt>Household cap</dt><dd>₹450.00</dd></div>
            <div><dt>Estimated delivery</dt><dd>Jul 20, 2026</dd></div>
            <div><dt>Requested by</dt><dd>Restock automation</dd></div>
          </dl>

          {adjusting ? (
            <AdjustAmount onCancel={() => setAdjusting(false)} onSubmit={(amount) => { setAdjusting(false); onAction(notification, "adjust", amount); }} />
          ) : (
            <div className="decision-actions" aria-label="Coffee purchase actions">
              {notification.actions.map((action) => (
                <button
                  key={action}
                  type="button"
                  className={`button ${action === "approve" ? "button--primary" : action === "skip" ? "button--quiet-danger" : "button--secondary"}`}
                  onClick={() => action === "adjust" ? setAdjusting(true) : onAction(notification, action)}
                  disabled={!actionable}
                >
                  {labels[action] || humanize(action)}
                </button>
              ))}
            </div>
          )}
          <p className="charge-note"><LockKey size={15} /> Approval creates a scoped Prava mandate. No real merchant charge occurs in this demo.</p>
        </>
      )}
    </article>
  );
}

function TeamsDecision({
  notification,
  onAction,
}: {
  notification: Notification;
  onAction: (notification: Notification, action: string) => void;
}) {
  const actionable = notification.status === "pending" || notification.status === "preview";
  return (
    <article className="decision decision--active decision--teams">
      <header className="decision-summary">
        <img src="/app/assets/teamtool-icon.png" alt="TeamTool collaboration icon" className="product-image" />
        <div className="decision-title-block">
          <div className="reason-row">
            <span className="attention-label attention-label--teams"><Clock size={15} weight="fill" /> Renewal due</span>
            <span className="reason-copy">Renews in 2 days</span>
          </div>
          <h2>TeamTool Pro · 1 seat</h2>
          <p className="teams-summary">Choose the current monthly plan or explicitly switch. Restock never switches plans from a generic approval.</p>
          <ModeBadge mode="disclosed_mock" label="Billing simulation · Explicit approval required" />
        </div>
        <div className="decision-time"><span>Jul 21</span><small>Renewal</small></div>
      </header>
      <div className="plan-comparison" role="group" aria-label="TeamTool renewal choices">
        <div className="plan-option plan-option--current"><span>Renew as-is</span><strong>$29</strong><small>Monthly · current plan</small></div>
        <div className="plan-option"><span>Switch plan</span><strong>$24</strong><small>Annual billing · saves $60/year</small></div>
      </div>
      <div className="decision-actions decision-actions--teams">
        {notification.actions.map((action) => (
          <button
            key={action}
            type="button"
            className={`button ${action === "renew_as_is" ? "button--teams" : action === "skip" ? "button--quiet-danger" : "button--secondary"}`}
            onClick={() => onAction(notification, action)}
            disabled={!actionable}
          >
            {labels[action] || humanize(action)}
          </button>
        ))}
      </div>
    </article>
  );
}

function SecondaryDecision({ kind }: { kind: "filter" | "paper" }) {
  const data = kind === "filter"
    ? { image: "/app/assets/water-filter.png", title: "RO water filter · due in 5 days", detail: "Replacement cartridge · 1 unit", price: "₹799 from Zepto" }
    : { image: "/app/assets/coffee-pouch.png", title: "Printer paper · monitored", detail: "A4 · 500 sheets", price: "₹650 last observed" };
  return (
    <article className="decision-row">
      <img src={data.image} alt="" className="row-image" />
      <div><h3>{data.title}</h3><p>{data.detail}</p><small>{data.price}</small></div>
      <span className="row-state">Watching</span>
      <button className="icon-button" type="button" aria-label={`Open ${data.title}`}><CaretDown size={18} /></button>
    </article>
  );
}

function ActivityView({ audit }: { audit: AuditEntry[] }) {
  return (
    <section className="activity-view" aria-labelledby="activity-title">
      <div className="page-heading">
        <div><p className="section-kicker">System record</p><h1 id="activity-title">Activity</h1><p>Every decision and payment boundary, in order.</p></div>
      </div>
      <div className="activity-table">
        {audit.length === 0 ? (
          <div className="empty-state"><Receipt size={28} /><h2>No live activity yet</h2><p>The audit trail will appear after the first workflow runs.</p></div>
        ) : audit.map((entry) => (
          <div className="activity-entry" key={entry.audit_id}>
            <CheckCircle size={19} weight="fill" />
            <div><strong>{humanize(entry.event_type)}</strong><small>{new Date(entry.created_at).toLocaleString()}</small></div>
            <ModeBadge mode={Object.values(entry.modes)[0] || "sandbox"} />
          </div>
        ))}
      </div>
    </section>
  );
}

function WorkflowRail({ notification, audit }: { notification?: Notification; audit: AuditEntry[] }) {
  const status = notification?.status || "preview";
  const completed = !["preview", "pending"].includes(status);
  const steps = [
    { label: "Detected", detail: "Inventory signal crossed", state: "done" },
    { label: "Decision requested", detail: "Approval needed", state: completed ? "done" : "current" },
    { label: "Approved", detail: completed ? humanize(status) : "Waiting", state: completed ? "current" : "waiting" },
    { label: "Order placed (simulated)", detail: "Waiting", state: "waiting" },
    { label: "Closed", detail: "Waiting", state: "waiting" },
  ];
  return (
    <aside className="workflow-rail" aria-label="Workflow and audit detail">
      <section className="rail-section">
        <div className="rail-heading"><div><h2>Workflow</h2><p>Decision timeline</p></div><Info size={18} /></div>
        <ol className="workflow-steps">
          {steps.map((step) => (
            <li className={`workflow-step workflow-step--${step.state}`} key={step.label}>
              <span className="step-marker" aria-hidden="true">{step.state === "done" ? <Check size={12} weight="bold" /> : ""}</span>
              <div><strong>{step.label}</strong><small>{step.detail}</small></div>
            </li>
          ))}
        </ol>
      </section>
      <section className="rail-section audit-section">
        <h2>Audit history</h2>
        <div className="rail-audit-list">
          {audit.length === 0 ? (
            <>
              <div><span className="audit-dot" /><p><strong>Decision requested</strong><small>Today, 10:24 AM · Restock</small></p></div>
              <div><span className="audit-dot" /><p><strong>Trigger detected</strong><small>Today, 10:24 AM · Automation</small></p></div>
            </>
          ) : audit.slice(0, 4).map((entry) => (
            <div key={entry.audit_id}><span className="audit-dot" /><p><strong>{humanize(entry.event_type)}</strong><small>{new Date(entry.created_at).toLocaleString()}</small></p></div>
          ))}
        </div>
      </section>
    </aside>
  );
}

export function LoginScreen({ onLogin }: { onLogin: (password: string) => Promise<void> }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onLogin(password);
      setPassword("");
    } catch {
      setPassword("");
      setError("That password was not accepted. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="login-card" aria-labelledby="login-title">
        <a className="brand-lockup login-brand" href="/app" aria-label="Restock home">
          <img src="/app/assets/restock-mark.png" alt="" className="brand-mark" />
          <span>Restock</span>
        </a>
        <p className="section-kicker">Private workspace</p>
        <h1 id="login-title">Welcome back</h1>
        <p className="login-copy">Sign in to review replenishment and billing decisions.</p>
        <form onSubmit={(event) => void submit(event)}>
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
          {error && <p className="login-error" role="alert">{error}</p>}
          <button className="login-submit" type="submit" disabled={busy || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="login-security"><LockKey size={15} /> Short-lived session · Password never stored</p>
      </section>
    </main>
  );
}

function AuthCheckingScreen() {
  return (
    <main className="login-shell" aria-busy="true">
      <section className="login-card login-card--checking">
        <a className="brand-lockup login-brand" href="/app" aria-label="Restock home">
          <img src="/app/assets/restock-mark.png" alt="" className="brand-mark" />
          <span>Restock</span>
        </a>
        <p className="login-copy">Checking your session…</p>
      </section>
    </main>
  );
}

export default function App() {
  const [view, setView] = useState<View>("home");
  const [notifications, setNotifications] = useState<Notification[]>(previews);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [status, setStatus] = useState("Preview ready");
  const [authState, setAuthState] = useState<"checking" | "required" | "ready">(
    import.meta.env.DEV ? "ready" : "checking",
  );

  const refresh = async () => {
    try {
      const caps = await api.capabilities();
      setCapabilities(caps);
      const [pending, events] = await Promise.all([api.notifications(), api.audit()]);
      if (pending.length) setNotifications(pending);
      setAudit(events);
      setAuthState("ready");
      setStatus(pending.length ? `${pending.length} decision${pending.length === 1 ? "" : "s"} waiting` : "Preview ready");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        await clearApiSessionToken();
        setAuthState("required");
        setStatus("Sign in required");
        return;
      }
      setStatus("Preview mode · API unavailable");
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

  const track: Track = view === "teams" ? "teams" : "home";
  const visible = useMemo(
    () => notifications.filter((notification) => (notification.track || (notification.actions.includes("switch_plan") ? "teams" : "home")) === track),
    [notifications, track],
  );
  const selected = visible[0];

  if (authState === "checking") return <AuthCheckingScreen />;

  if (authState === "required") {
    return <LoginScreen onLogin={async (password) => {
      await api.login(password);
      setAuthState("checking");
      await refresh();
    }} />;
  }

  const act = async (notification: Notification, action: string, adjustedAmount?: string) => {
    if (notification.status === "preview") {
      setNotifications((items) => items.map((item) => item.notification_id === notification.notification_id ? { ...item, status: action } : item));
      setStatus(`Preview recorded · ${humanize(action)}`);
      return;
    }
    try {
      const run = await api.action(notification.run_id, action, adjustedAmount);
      if (run.state === "passkey_pending") {
        const { approval_url } = await api.approvalUrl(notification.run_id);
        window.open(approval_url, "_blank", "noopener,noreferrer");
        setStatus("Passkey opened · Return after approval");
      } else {
        setStatus(`Workflow · ${humanize(run.state)}`);
      }
      await refresh();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        await clearApiSessionToken();
        setAuthState("required");
        setStatus("Sign in required");
        return;
      }
      setStatus(error instanceof Error ? error.message : "Action failed");
    }
  };

  return (
    <div className="app-frame">
      <AppHeader capabilities={capabilities} />
      <Sidebar view={view} setView={setView} capabilities={capabilities} />
      <main className="main-content">
        {view === "activity" ? (
          <ActivityView audit={audit} />
        ) : (
          <>
            <DecisionHeader track={track} status={status} />
            <section className="decision-list" aria-label={`${track} decisions`}>
              {selected && track === "home" && <HomeDecision capabilities={capabilities} notification={selected} onAction={(notification, action, amount) => void act(notification, action, amount)} />}
              {selected && track === "teams" && <TeamsDecision notification={selected} onAction={(notification, action) => void act(notification, action)} />}
              {track === "home" && <><SecondaryDecision kind="filter" /><SecondaryDecision kind="paper" /></>}
            </section>
            <footer className="list-footer"><span>All times in Asia/Kolkata (IST)</span><span>Updated automatically</span></footer>
          </>
        )}
      </main>
      <WorkflowRail notification={selected} audit={audit} />
    </div>
  );
}
