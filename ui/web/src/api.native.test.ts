import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const native = vi.hoisted(() => ({
  token: "rst1.native.signature" as string | null,
  saveSessionToken: vi.fn(),
  clearSessionToken: vi.fn(),
}));

vi.mock("./native", () => ({
  isNative: () => true,
  loadSessionToken: vi.fn(async () => native.token),
  saveSessionToken: native.saveSessionToken,
  clearSessionToken: native.clearSessionToken,
}));

import {
  api,
  clearApiSessionToken,
  loadApiSessionToken,
  storeApiSessionToken,
} from "./api";

describe("native API authentication", () => {
  beforeEach(() => {
    native.token = "rst1.native.signature";
    native.saveSessionToken.mockReset();
    native.clearSessionToken.mockReset();
  });

  afterEach(() => vi.unstubAllGlobals());

  it("retains bearer sessions in native secure storage", async () => {
    await storeApiSessionToken("rst1.new-native.signature");

    expect(native.saveSessionToken).toHaveBeenCalledWith("rst1.new-native.signature");
    expect(await loadApiSessionToken()).toBe("rst1.native.signature");

    await clearApiSessionToken();
    expect(native.clearSessionToken).toHaveBeenCalledOnce();
  });

  it("sends the native secure-storage bearer on mutating requests", async () => {
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
        headers: expect.objectContaining({
          Authorization: "Bearer rst1.native.signature",
        }),
      }),
    );
  });
});
