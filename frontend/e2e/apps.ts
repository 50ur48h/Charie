import { expect, type Page } from "@playwright/test";

export const CHAT = "http://localhost:4173";
export const LEARNER = "http://localhost:4174";

export const SAMPLE_PASSWORD = "bella-forno";

// Signs in through the real login form, then checks we landed where asked.
// Goes to the target first so the guard remembers it as the way back.
export async function signedIn(page: Page, app: string, target = "/"): Promise<void> {
  await page.goto(`${app}${target}`);
  await expect(page).toHaveURL(`${app}/login`);
  await page.getByLabel("Password", { exact: true }).fill(SAMPLE_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(`${app}${target}`);
}
