import { useEffect, useMemo, useState } from "react";
import { api, type AuditEntry, type Capabilities, type Notification } from "./api";

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
  approve: "Approve",
  adjust: "Adjust",
  skip: "Skip",
  renew_as_is: "Renew as-is",
  switch_plan: "Switch plan",
};

export default function App() {
  const [track, setTrack] = useState<"home" | "teams">("home");
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [status, setStatus] = useState("Checking for proactive triggers…");

  const refresh = async () => {
    try {
      const [caps, pending, events] = await Promise.all([api.capabilities(), api.notifications(), api.audit()]);
      setCapabilities(caps);
      setNotifications(pending.length ? pending : previews);
      setAudit(events);
      setStatus(pending.length ? `${pending.length} decision${pending.length === 1 ? "" : "s"} waiting` : "Preview mode — connect the worker to receive live triggers");
    } catch {
      setNotifications(previews);
      setStatus("Preview mode — API is unavailable");
    }
  };

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, []);

  const visible = useMemo(
    () => notifications.filter((notification) => (notification.track || (notification.actions.includes("switch_plan") ? "teams" : "home")) === track),
    [notifications, track],
  );

  const act = async (notification: Notification, action: string) => {
    if (notification.status === "preview") {
      setNotifications((items) => items.map((item) => item.notification_id === notification.notification_id ? { ...item, status: action } : item));
      setStatus(`Preview action recorded: ${labels[action]}`);
      return;
    }
    try {
      const adjusted = action === "adjust" ? window.prompt("New maximum amount") || undefined : undefined;
      const run = await api.action(notification.run_id, action, adjusted);
      if (run.state === "passkey_pending") {
        const { approval_url } = await api.approvalUrl(notification.run_id);
        window.open(approval_url, "_blank", "noopener,noreferrer");
        setStatus("Passkey approval opened — return here after approving");
      } else {
        setStatus(`Workflow is now ${run.state.replaceAll("_", " ")}`);
      }
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Action failed");
    }
  };

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand"><span className="mark">R</span><div><strong>Restock</strong><small>Proactive commerce, bounded by you</small></div></div>
        <div className="badges">
          <span>{capabilities?.prava_mode || "sandbox"}</span>
          <span>{capabilities?.home_merchant_mode || "disclosed_mock"}</span>
        </div>
      </header>

      <section className="hero">
        <p className="eyebrow">Restock caught it first</p>
        <h1>Nothing to remember.<br />Nothing charged silently.</h1>
        <p>{status}</p>
      </section>

      <nav className="track-tabs" aria-label="Restock track">
        <button className={track === "home" ? "active" : ""} onClick={() => setTrack("home")}><span>Home</span><small>WhatsApp-style</small></button>
        <button className={track === "teams" ? "active" : ""} onClick={() => setTrack("teams")}><span>Teams</span><small>Slack-style</small></button>
      </nav>

      <section className={`conversation ${track}`} aria-live="polite">
        <div className="channel-label">{track === "home" ? "WhatsApp interaction preview" : "Slack approval surface"}<span>disclosed surface</span></div>
        {visible.map((notification) => (
          <article className="message" key={notification.notification_id}>
            <div className="avatar">R</div>
            <div className="bubble">
              <p>{notification.message}</p>
              <div className="actions">
                {notification.actions.map((action) => (
                  <button key={action} onClick={() => void act(notification, action)} disabled={notification.status !== "pending" && notification.status !== "preview"}>
                    {labels[action] || action}
                  </button>
                ))}
              </div>
              <small>{notification.status === "preview" ? "Preview data" : notification.status}</small>
            </div>
          </article>
        ))}
      </section>

      <aside className="audit-panel">
        <div><p className="eyebrow">Proof, not promises</p><h2>Audit & savings</h2></div>
        <div className="audit-list">
          {audit.length === 0 ? <p>No completed live workflows yet. The trace appears here after approval.</p> : audit.slice(0, 5).map((entry) => (
            <div key={entry.audit_id}><strong>{entry.event_type.replaceAll("_", " ")}</strong><small>{new Date(entry.created_at).toLocaleString()}</small></div>
          ))}
        </div>
      </aside>
    </main>
  );
}
