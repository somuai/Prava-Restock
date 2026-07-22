import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoginScreen } from "./App";
import { clearApiSessionToken, loadApiSessionToken, storeApiSessionToken } from "./api";


describe("production login surface", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a restrained password-only login form", () => {
    const markup = renderToStaticMarkup(<LoginScreen onLogin={async () => undefined} />);

    expect(markup).toContain("Welcome back");
    expect(markup).toContain('type="password"');
    expect(markup).toContain('autoComplete="current-password"');
    expect(markup).not.toContain("API token");
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
});
