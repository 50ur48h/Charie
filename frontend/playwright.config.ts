import { defineConfig, devices } from "@playwright/test";

const ci = !!process.env.CI;

export default defineConfig({
  testDir: "e2e",
  // The real-mode journeys live here too but only run on the laptop
  // through playwright.real.config.ts (scripts/e2e_real.py run).
  testIgnore: ["real/**"],
  retries: ci ? 1 : 0,
  reporter: [["html", { open: "never" }]],
  use: {
    trace: "retain-on-failure",
    contextOptions: { reducedMotion: "reduce" },
  },
  reportSlowTests: null,
  projects: [
    {
      name: "laptop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "tablet",
      use: { ...devices["Desktop Chrome"], viewport: { width: 820, height: 1180 } },
    },
    {
      name: "phone",
      use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: [
    {
      command: "npm run preview:mock -w @charie/chat",
      url: "http://localhost:4173",
      reuseExistingServer: !ci,
    },
    {
      command: "npm run preview:mock -w @charie/learner",
      url: "http://localhost:4174",
      reuseExistingServer: !ci,
    },
  ],
});
