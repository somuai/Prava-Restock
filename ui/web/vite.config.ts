import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/app/",
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/capabilities": "http://localhost:8000",
    },
  },
});
