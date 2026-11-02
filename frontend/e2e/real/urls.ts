import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, type Page } from "@playwright/test";

const here = dirname(fileURLToPath(import.meta.url));
const REPO = join(here, "..", "..");

export const CHAT = "http://localhost:8001";
export const LEARNER = "http://localhost:8002";
export const E2E_PASSWORD = "e2e-password";

// The journeys need the throwaway database; the AI ones also need the
// saved replies from a --record run (P12.4 Task 6, needs your yes).
export function dumpPath(): string {
  return join(REPO, "backend", "tests", "replays", "e2e-db.dump");
}

export function recordingsPath(): string {
  return join(REPO, "backend", "tests", "replays", "e2e-journeys.ready");
}

export function recordingsReady(): boolean {
  return existsSync(recordingsPath()) || process.env.E2E_RECORDING === "1";
}

// Signs in through the real login form on the throwaway database. The
// app decides where to land (the setup guide resolves ?step=n itself),
// so this only proves we left the login page.
export async function signedIn(page: Page, app: string, target = "/"): Promise<void> {
  await page.goto(`${app}${target}`);
  await expect(page).toHaveURL(`${app}/login`);
  await page.getByLabel("Password", { exact: true }).fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).not.toHaveURL(`${app}/login`);
}
