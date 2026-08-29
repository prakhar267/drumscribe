import { defineConfig, devices } from "@playwright/test";

const fullStack = process.env.DRUMSCRIBE_FULL_STACK_E2E === "1";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL: fullStack ? "http://localhost:3000" : "http://127.0.0.1:3100",
    trace: "on-first-retry",
  },
  webServer: fullStack ? undefined : {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testIgnore: /editor/ },
  ],
});
