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

  it("labels isolated temporary access without exposing owner wording", () => {
    const markup = renderToStaticMarkup(
      <LoginScreen
        authMode="hybrid"
        reviewerAccess
        googleClientId="google-client-id"
        onGoogleLogin={async () => undefined}
        onPasswordLogin={async () => undefined}
      />,
    );

    expect(markup).toContain("Prava reviewer access");
    expect(markup).toContain("pre-seeded review pantry");
    expect(markup).toContain("Reviewer password");
    expect(markup).not.toContain("Owner recovery access");
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

  it("never persists bearer sessions in browser storage", async () => {
    const sessionStorage = {
      getItem: vi.fn(() => "legacy-browser-token"),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
      key: () => null,
      length: 0,
    } satisfies Storage;
    const localStorage = { getItem: vi.fn(), setItem: vi.fn(), removeItem: vi.fn() };
    vi.stubGlobal("window", { sessionStorage, localStorage });

    await storeApiSessionToken("rst1.test.signature");

    expect(await loadApiSessionToken()).toBeNull();
    expect(sessionStorage.getItem).not.toHaveBeenCalled();
    expect(sessionStorage.setItem).not.toHaveBeenCalled();
    expect(localStorage.setItem).not.toHaveBeenCalled();

    await clearApiSessionToken();
    expect(sessionStorage.removeItem).toHaveBeenCalledWith("restock_session");
  });

  it("posts the Google credential with cookies enabled without persisting the returned bearer", async () => {
    const sessionStorage = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
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
    expect(await loadApiSessionToken()).toBeNull();
    expect(sessionStorage.setItem).not.toHaveBeenCalled();
  });

  it("links Google in the browser through the HttpOnly cookie only", async () => {
    const sessionStorage = {
      getItem: vi.fn(() => "legacy-browser-token"),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
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
        headers: expect.not.objectContaining({ Authorization: expect.anything() }),
        body: JSON.stringify({ credential: "fresh-google-credential" }),
      }),
    );
    expect(sessionStorage.getItem).not.toHaveBeenCalled();
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
