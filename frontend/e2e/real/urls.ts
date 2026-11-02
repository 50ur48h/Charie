import { expect, type Page } from "@playwright/test";
import {
  dumpPath,
  recordingsPath,
  recordingsReady,
} from "../../shared/src/e2e-real/paths";

export { dumpPath, recordingsPath, recordingsReady };

export const CHAT = "http://localhost:8001";
export const LEARNER = "http://localhost:8002";
export const E2E_PASSWORD = "e2e-password";

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
