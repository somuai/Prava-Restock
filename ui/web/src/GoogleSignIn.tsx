import { useEffect, useRef, useState } from "react";

type GoogleCredentialResponse = {
  credential?: string;
};

type GoogleIdentity = {
  initialize: (config: {
    client_id: string;
    callback: (response: GoogleCredentialResponse) => void;
    ux_mode: "popup";
  }) => void;
  renderButton: (
    parent: HTMLElement,
    options: {
      type: "standard";
      theme: "outline";
      size: "large";
      text: "continue_with";
      shape: "pill";
      logo_alignment: "left";
      width: number;
    },
  ) => void;
};

declare global {
  interface Window {
    google?: {
      accounts: {
        id: GoogleIdentity;
      };
    };
  }
}

const GOOGLE_SCRIPT_ID = "google-identity-services";
const GOOGLE_LOAD_TIMEOUT_MS = 8_000;
let googleIdentityPromise: Promise<GoogleIdentity> | null = null;

function loadGoogleIdentity(): Promise<GoogleIdentity> {
  if (window.google?.accounts.id) return Promise.resolve(window.google.accounts.id);
  if (googleIdentityPromise) return googleIdentityPromise;

  const pending = new Promise<GoogleIdentity>((resolve, reject) => {
    let settled = false;
    let pollTimer: number | undefined;
    let timeoutTimer: number | undefined;

    const cleanup = () => {
      if (pollTimer !== undefined) window.clearInterval(pollTimer);
      if (timeoutTimer !== undefined) window.clearTimeout(timeoutTimer);
    };
    const finish = () => {
      const identity = window.google?.accounts.id;
      if (!identity || settled) return;
      settled = true;
      cleanup();
      resolve(identity);
    };
    const fail = () => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(new Error("Google sign-in could not be loaded. Check your connection and try again."));
    };
    const observeGoogle = () => {
      finish();
    };
    const existing = document.getElementById(GOOGLE_SCRIPT_ID) as HTMLScriptElement | null;
    if (existing) {
      // The script may have loaded just before this component mounted.  In
      // that case there is no second load event, so check the global as well.
      existing.addEventListener("load", observeGoogle, { once: true });
      existing.addEventListener("error", fail, { once: true });
      observeGoogle();
      if (!settled) {
        pollTimer = window.setInterval(observeGoogle, 50);
        timeoutTimer = window.setTimeout(fail, GOOGLE_LOAD_TIMEOUT_MS);
      }
      return;
    }

    const script = document.createElement("script");
    script.id = GOOGLE_SCRIPT_ID;
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.addEventListener("load", observeGoogle, { once: true });
    script.addEventListener("error", fail, { once: true });
    document.head.appendChild(script);
    pollTimer = window.setInterval(observeGoogle, 50);
    timeoutTimer = window.setTimeout(fail, GOOGLE_LOAD_TIMEOUT_MS);
  }).catch((error) => {
    googleIdentityPromise = null;
    throw error;
  });
  googleIdentityPromise = pending;
  return pending;
}

export function GoogleSignIn({
  clientId,
  onCredential,
  mode = "signin",
}: {
  clientId: string;
  onCredential: (credential: string) => Promise<void>;
  mode?: "signin" | "link";
}) {
  const buttonRef = useRef<HTMLDivElement>(null);
  const credentialHandler = useRef(onCredential);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    credentialHandler.current = onCredential;
  }, [onCredential]);

  useEffect(() => {
    if (!clientId) {
      setError("Google sign-in is not configured for this environment yet.");
      return;
    }
    setError("");

    let active = true;
    let resizeObserver: ResizeObserver | null = null;

    void loadGoogleIdentity()
      .then((identity) => {
        if (!active || !buttonRef.current) return;
        identity.initialize({
          client_id: clientId,
          callback: ({ credential }) => {
            if (!credential || !active) {
              setError("Google did not return a sign-in credential. Please try again.");
              return;
            }
            setBusy(true);
            setError("");
            void credentialHandler.current(credential)
              .then(() => {
                if (!active) return;
                setBusy(false);
                if (mode === "link") setSuccess(true);
              })
              .catch((reason: unknown) => {
                if (!active) return;
                const message = reason instanceof Error ? reason.message : "Google sign-in failed.";
                setError(message);
                setBusy(false);
              });
          },
          ux_mode: "popup",
        });

        const render = () => {
          const target = buttonRef.current;
          if (!target) return;
          const width = Math.max(220, Math.min(400, Math.floor(target.clientWidth)));
          target.replaceChildren();
          identity.renderButton(target, {
            type: "standard",
            theme: "outline",
            size: "large",
            text: "continue_with",
            shape: "pill",
            logo_alignment: "left",
            width,
          });
        };

        render();
        resizeObserver = new ResizeObserver(render);
        resizeObserver.observe(buttonRef.current);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Google sign-in could not be loaded.");
      });

    return () => {
      active = false;
      resizeObserver?.disconnect();
    };
  }, [clientId, mode]);

  return (
    <div
      className="google-signin"
      data-mode={mode}
      data-status={success ? "success" : error ? "error" : busy ? "busy" : "idle"}
    >
      <div
        className="google-signin-button"
        ref={buttonRef}
        aria-label={mode === "link" ? "Link Google sign-in" : "Continue with Google"}
        aria-busy={busy}
        hidden={success}
      />
      <p className="google-signin-status" aria-live="polite">
        {success
          ? "Google sign-in is now linked to this Restock account."
          : busy
            ? (mode === "link" ? "Linking Google sign-in…" : "Opening your pantry…")
            : error}
      </p>
    </div>
  );
}
