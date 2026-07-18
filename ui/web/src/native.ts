import { App } from "@capacitor/app";
import { Capacitor } from "@capacitor/core";
import { PushNotifications } from "@capacitor/push-notifications";
import { KeychainAccess, SecureStorage } from "@aparajita/capacitor-secure-storage";

const SESSION_KEY = "restock_session";

export const isNative = () => Capacitor.isNativePlatform();

export function approvalRunId(url: string): string | null {
  const parsed = new URL(url);
  return parsed.protocol === "restock:" && parsed.hostname === "approval"
    ? parsed.searchParams.get("run_id")
    : null;
}

export async function saveSessionToken(token: string): Promise<void> {
  if (!isNative()) throw new Error("Native secure storage is unavailable on the web");
  await SecureStorage.setKeyPrefix("space.prava.restock.");
  await SecureStorage.set(SESSION_KEY, token, true, false, KeychainAccess.whenUnlockedThisDeviceOnly);
}

export async function loadSessionToken(): Promise<string | null> {
  if (!isNative()) return null;
  await SecureStorage.setKeyPrefix("space.prava.restock.");
  const value = await SecureStorage.get(SESSION_KEY);
  return typeof value === "string" ? value : null;
}

export async function initializeNative(
  onApprovalReturn: (runId: string) => Promise<void>,
  onPushToken?: (token: string) => Promise<void>,
): Promise<() => void> {
  if (!isNative()) return () => undefined;
  const deepLink = await App.addListener("appUrlOpen", ({ url }) => {
    const runId = approvalRunId(url);
    if (runId) void onApprovalReturn(runId);
  });
  const registration = await PushNotifications.addListener("registration", ({ value }) => {
    if (onPushToken) void onPushToken(value);
  });
  const action = await PushNotifications.addListener("pushNotificationActionPerformed", ({ notification }) => {
    const runId = String(notification.notification.data?.run_id || "");
    if (runId) void onApprovalReturn(runId);
  });
  const permission = await PushNotifications.requestPermissions();
  if (permission.receive === "granted") await PushNotifications.register();
  return () => {
    void deepLink.remove();
    void registration.remove();
    void action.remove();
  };
}
