import { defineConfig } from "@playwright/test";

// Smoke tests run against a real server (the built container in CI): same origin, same CSP.
//   docker run ... -p 10000:10000 snazzlebop   then   npm run e2e
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  fullyParallel: false,
  workers: 1, // one client IP: run viewports one after another to stay inside the real rate limits
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:10000",
    browserName: "chromium",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "mobile", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 3 } },
    { name: "desktop", use: { viewport: { width: 1280, height: 800 } } },
  ],
});
