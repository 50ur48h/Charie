/** The Phase 11 gate's smoke: a browser driving the real product (plan WP11.2b). */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e-compose",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  // No retries, deliberately, where the hermetic suite takes one.
  retries: 0,
  reporter: "list",
  use: {
    baseURL: process.env.SMOKE_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // Generous, and every second of it is real work rather than slack.
  expect: { timeout: 30_000 },
  timeout: 5 * 60_000,
});
