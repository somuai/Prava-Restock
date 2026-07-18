import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "space.prava.restock",
  appName: "Restock",
  webDir: "dist",
  server: { androidScheme: "https" },
};

export default config;
