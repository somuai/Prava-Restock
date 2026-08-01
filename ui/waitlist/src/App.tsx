import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ArrowRight, Check, X } from "@phosphor-icons/react";

type DialogStage = "email" | "complete";

interface WaitlistPayload {
  email: string;
  company?: string;
  client_started_at?: string;
  landing_variant?: string;
  entry_demo_track?: string;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

async function joinWaitlist(payload: WaitlistPayload): Promise<void> {
  const response = await fetch("/api/v1/waitlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let message = "We couldn’t save your place. Please try again.";
    try {
      const body = (await response.json()) as { detail?: string; message?: string };
      message = body.detail || body.message || message;
    } catch {
      // The generic error is intentionally safe for non-JSON upstream failures.
    }
    throw new Error(message);
  }
}

function Brand() {
  return (
    <a className="brand" href="/" aria-label="Restock home">
      <img src="/assets/restock-mark.png" alt="" />
      <span>restock.</span>
    </a>
  );
}

function WaitlistDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const startedAtRef = useRef(new Date().toISOString());
  const [stage, setStage] = useState<DialogStage>("email");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    returnFocusRef.current = document.activeElement as HTMLElement | null;
    document.body.classList.add("dialog-open");

    const frame = window.requestAnimationFrame(() => {
      dialogRef.current?.querySelector<HTMLInputElement>("#waitlist-email")?.focus();
    });

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href]',
        ),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.body.classList.remove("dialog-open");
      document.removeEventListener("keydown", onKeyDown);
      returnFocusRef.current?.focus();
    };
  }, [onClose, open]);

  useEffect(() => {
    if (open) return;
    const timer = window.setTimeout(() => {
      setStage("email");
      setError("");
      setBusy(false);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [open]);

  if (!open) return null;

  async function submitEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const normalizedEmail = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      setError("Enter a valid email address.");
      return;
    }

    setBusy(true);
    try {
      await joinWaitlist({
        email: normalizedEmail,
        company,
        client_started_at: startedAtRef.current,
        landing_variant: "your-pantry-before-it-runs-out",
        entry_demo_track: "home",
      });
      setEmail(normalizedEmail);
      setStage("complete");
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "We couldn’t save your place. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="waitlist-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <div className="dialog-brand">
          <img src="/assets/restock-mark-white.png" alt="" />
        </div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="Close waitlist">
          <X weight="bold" aria-hidden="true" />
        </button>

        {stage === "email" && (
          <>
            <h2 id={titleId}>Join the waitlist.</h2>
            <p id={descriptionId} className="dialog-copy">
              Leave your email. We’ll tell you when Restock is ready to try.
            </p>
            <form className="dialog-form" onSubmit={submitEmail} noValidate>
              <label htmlFor="waitlist-email">Email address</label>
              <input
                id="waitlist-email"
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? "waitlist-error" : undefined}
                placeholder="you@email.com"
                required
              />
              <div className="honeypot" aria-hidden="true">
                <label htmlFor="waitlist-company">Company</label>
                <input
                  id="waitlist-company"
                  name="company"
                  value={company}
                  onChange={(event) => setCompany(event.target.value)}
                  tabIndex={-1}
                  autoComplete="off"
                />
              </div>
              {error && (
                <p className="form-error" id="waitlist-error" role="alert">
                  {error}
                </p>
              )}
              <button className="primary-button form-submit" type="submit" disabled={busy}>
                <span>{busy ? "Saving…" : "Join the waitlist"}</span>
                {!busy && <ArrowRight weight="bold" aria-hidden="true" />}
              </button>
            </form>
            <p className="dialog-footnote">We’ll only use this email for Restock updates.</p>
          </>
        )}

        {stage === "complete" && (
          <div className="success-state">
            <div className="success-mark">
              <Check weight="bold" aria-hidden="true" />
            </div>
            <h2 id={titleId}>You’re in.</h2>
            <p id={descriptionId} className="dialog-copy">
              We’ll email you when Restock is ready to try.
            </p>
            <button className="primary-button form-submit" type="button" onClick={onClose}>
              Done
            </button>
          </div>
        )}

        <nav className="dialog-legal" aria-label="Legal">
          <a href="/app/privacy.html">Privacy</a>
          <span aria-hidden="true">·</span>
          <a href="/app/terms.html">Terms</a>
        </nav>
      </div>
    </div>
  );
}

export function App() {
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <>
      <main className="waitlist-page">
        <section className="copy-panel" aria-labelledby="waitlist-heading">
          <header>
            <Brand />
            <a className="header-link" href="/app/">
              Sign in
            </a>
          </header>

          <div className="hero-copy">
            <h1 id="waitlist-heading">Your pantry, before it runs out.</h1>
            <p className="lead">
              Restock watches what is running low, checks the current price, and asks before anything
              is bought.
            </p>
            <button className="primary-button hero-button" type="button" onClick={() => setDialogOpen(true)}>
              <span>Join the waitlist</span>
              <ArrowRight weight="bold" aria-hidden="true" />
            </button>
            <p className="trust-line">Just your email. We’ll let you know when Restock is ready.</p>
          </div>

          <footer className="page-footer">
            <span>Restock Home · Restock Teams</span>
            <nav aria-label="Legal">
              <a href="/app/privacy.html">Privacy</a>
              <a href="/app/terms.html">Terms</a>
            </nav>
          </footer>
        </section>

        <section className="proof-panel" aria-label="Restock feature preview">
          <div className="video-frame">
            <video
              autoPlay
              muted
              loop
              playsInline
              preload="metadata"
              poster="/media/restock-feature-poster.png"
              aria-label="Animated preview of a Restock item moving from tracked to triggered, quoted, approved, and restocked"
            >
              <source src="/media/restock-feature-demo.mp4" type="video/mp4" />
            </video>
            <noscript>
              <img
                src="/media/restock-feature-poster.png"
                alt="Restock purchase preview showing the item, quote, approval controls, and restocked state"
              />
            </noscript>
          </div>
        </section>
      </main>
      <WaitlistDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />
    </>
  );
}
