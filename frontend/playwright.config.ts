import { defineConfig, devices } from "@playwright/test";

const apiPort = process.env.API_PORT ?? "8000";
const webPort = process.env.WEB_PORT ?? "5173";
const reuse = Boolean(process.env.E2E_REUSE);
// Only for a machine whose preinstalled Chromium is a different revision than this Playwright wants.
const executablePath = process.env.PW_CHROMIUM_PATH;
const desktop = { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } };

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${webPort}`,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: executablePath ? { executablePath } : {},
  },
  // The full games measure first-chunk latency, so they run before the spoiler scans load the
  // one replay backend with three more games and the leak checker.
  projects: [
    { name: "desktop", use: desktop, testMatch: /full-game|verify/ },
    { name: "phone", use: { ...devices["Pixel 7"] }, testMatch: /full-game|verify/ },
    {
      name: "spoilers",
      use: desktop,
      testMatch: /no-spoilers/,
      dependencies: ["desktop", "phone"],
    },
  ],
  webServer: [
    {
      command: "make -C .. e2e-backend",
      url: `http://localhost:${apiPort}/healthz`,
      timeout: 180_000,
      reuseExistingServer: reuse,
    },
    {
      command: "npx vite build && npx vite preview",
      url: `http://localhost:${webPort}`,
      timeout: 120_000,
      reuseExistingServer: reuse,
    },
  ],
});
