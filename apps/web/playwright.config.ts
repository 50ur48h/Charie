/** Browser tests for the screens the unit tests cannot honestly cover. */

import { defineConfig, devices } from "@playwright/test";

import { STUB_PORT } from "./e2e/stub-api";

const PORT = 3100;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "list" : [["list"]],
  // `localhost`, not `127.0.0.1`: Next dev blocks cross-origin requests to dev-only assets.
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // A real browser against a real server.
  expect: { timeout: 20_000 },
  // Built once and served, not `next dev`.
  webServer: {
    command: `pnpm exec next build && pnpm exec next start --port ${PORT}`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 300_000,
    env: {
      // Development sign-in, so a real browser holds a real session without an identity provider.
      NEXT_PUBLIC_ENV: "ci",
      NEXT_PUBLIC_AUTH_MODE: "dev",
      NEXT_PUBLIC_API_URL: `http://127.0.0.1:${STUB_PORT}`,
    },
  },
});
