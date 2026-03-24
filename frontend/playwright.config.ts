import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3001",
    channel: "chrome",
    headless: true,
    screenshot: "only-on-failure",
    trace: "on-first-retry",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: "bash ../scripts/run_e2e_api.sh",
      url: "http://127.0.0.1:8001/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "bash scripts/run_e2e_frontend.sh",
      url: "http://127.0.0.1:3001/auth/login",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
