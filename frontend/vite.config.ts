import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: the Vite server proxies API + WebSocket traffic to the FastAPI backend so the
// app is same-origin in dev too (no CORS, same code path as production).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
    // The production CSP has no inline sources: never inline assets as data: URIs.
    assetsInlineLimit: 0,
    cssCodeSplit: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/healthz": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
