import path from "node:path";

import { defineConfig } from "@playwright/test";

const frontendDir = __dirname;
const rootDir = path.resolve(frontendDir, "..");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  // The first navigation waits for the Next.js dev server to compile the page,
  // which can push a step past the 10s expect timeout on a cold CI runner.
  retries: process.env.CI ? 1 : 0,
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
      command: "bash scripts/run_e2e_api.sh",
      cwd: rootDir,
      url: "http://127.0.0.1:8001/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "bash scripts/run_e2e_frontend.sh",
      cwd: frontendDir,
      url: "http://127.0.0.1:3001/auth/login",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
