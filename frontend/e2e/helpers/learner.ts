import { expect, type Page } from "@playwright/test";
import { LEARNER, SAMPLE_PASSWORD } from "../apps";

// Opens a learner page in a named mock world: signs in at /login?mock=<world>
// (the store resets once at that page load), then opens the path in the same
// world. "still" is the design world with timers off; "new" is empty.
export async function openLearner(
  page: Page,
  path = "/sources",
  world: "new" | "still" = "still",
): Promise<void> {
  await page.goto(`${LEARNER}/login?mock=${world}`);
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await page.getByLabel("Password", { exact: true }).fill(SAMPLE_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  // The index route drops the query when it forwards to /setup; the store
  // was already reset at the login page load, so going explicit is enough.
  await expect(page).toHaveURL(`${LEARNER}/setup`);
  await page.goto(`${LEARNER}${path}?mock=${world}`);
}
