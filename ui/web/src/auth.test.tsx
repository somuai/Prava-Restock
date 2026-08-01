import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoginScreen } from "./App";
import { api, clearApiSessionToken, loadApiSessionToken, storeApiSessionToken } from "./api";
import { GoogleSignIn } from "./GoogleSignIn";


describe("production login surface", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders Google as the only sign-in method in google mode", () => {
    const markup = renderToStaticMarkup(
      <LoginScreen
        authMode="google"
        googleClientId="google-client-id"
        onGoogleLogin={async () => undefined}
      />,
    );

    expect(markup).toContain("Your pantry is waiting");
    expect(markup).toContain("Continue with Google");
    expect(markup).toContain("never sees or stores your Google password");
    expect(markup).toContain('href="/app/terms.html"');
    expect(markup).toContain('href="/app/privacy.html"');
    expect(markup).not.toContain('type="password"');
    expect(markup).not.toContain("API token");
  });

  it("keeps password access collapsed and explicitly marked as recovery in hybrid mode", () => {
    const markup = renderToStaticMarkup(
      <LoginScreen
        authMode="hybrid"
        googleClientId="google-client-id"
        onGoogleLogin={async () => undefined}
        onPasswordLogin={async () => undefined}
      />,
    );

    expect(markup).toContain("Owner recovery access");
    expect(markup).toContain('type="password"');
    expect(markup).toContain('autoComplete="current-password"');
  });

  it("keeps the configured password fallback usable in solo mode", () => {
    const markup = renderToStaticMarkup(
      <LoginScreen
        authMode="solo"
        googleClientId=""
        onGoogleLogin={async () => undefined}
        onPasswordLogin={async () => undefined}
      />,
    );

    expect(markup).toContain('type="password"');
    expect(markup).toContain(">Sign in</button>");
    expect(markup).not.toContain("Continue with Google");
    expect(markup).not.toContain("Owner recovery access");
  });

  it("stores web sessions only in session storage", async () => {
    const values = new Map<string, string>();
    const sessionStorage = {
      getItem: (key: string) => values.get(key) || null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
      key: () => null,
      length: 0,
    } satisfies Storage;
    const localStorage = { setItem: vi.fn() };
    vi.stubGlobal("window", { sessionStorage, localStorage });

    await storeApiSessionToken("rst1.test.signature");

    expect(await loadApiSessionToken()).toBe("rst1.test.signature");
    expect(localStorage.setItem).not.toHaveBeenCalled();

    await clearApiSessionToken();
    expect(await loadApiSessionToken()).toBeNull();
  });

  it("posts the Google credential with cookies enabled and preserves bearer storage", async () => {
    const values = new Map<string, string>();
    const sessionStorage = {
      getItem: (key: string) => values.get(key) || null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
      key: () => null,
      length: 0,
    } satisfies Storage;
    vi.stubGlobal("window", { sessionStorage });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: "rst1.google.signature",
        token_type: "bearer",
        expires_in: 3600,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.googleLogin("google-id-credential");

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/google"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ credential: "google-id-credential" }),
      }),
    );
    expect(await loadApiSessionToken()).toBe("rst1.google.signature");
  });

  it("links Google only through the current authenticated session", async () => {
    const values = new Map<string, string>([["restock_session", "rst1.owner.signature"]]);
    const sessionStorage = {
      getItem: (key: string) => values.get(key) || null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
      key: () => null,
      length: 1,
    } satisfies Storage;
    vi.stubGlobal("window", { sessionStorage });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: "linked", provider: "google" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.googleLink("fresh-google-credential");

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/google/link"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({ Authorization: "Bearer rst1.owner.signature" }),
        body: JSON.stringify({ credential: "fresh-google-credential" }),
      }),
    );
  });

  it("labels the official Google surface as a link action in profile mode", () => {
    const markup = renderToStaticMarkup(
      <GoogleSignIn
        clientId="google-client-id"
        mode="link"
        onCredential={async () => undefined}
      />,
    );

    expect(markup).toContain("Link Google sign-in");
    expect(markup).toContain('data-mode="link"');
  });
});
