import { defineConfig, devices } from "@playwright/test";

// The real-mode suite (P12.4): both apps served by their own APIs on the
// throwaway database (scripts/e2e_real.py run), with saved AI replies.
export default defineConfig({
  testDir: "./e2e/real",
  workers: 1,
  fullyParallel: false,
  timeout: 180000,
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
      name: "phone",
      use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 } },
    },
  ],
});
