import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

// P03.13 settings on the mocked API: preferences, password, memories, sign out.

test.beforeEach(async ({ page }) => {
  await signedIn(page, CHAT, "/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
});

test("preferences_reload keeps every saved preference", async ({ page }) => {
  await page.getByRole("button", { name: "Detailed", exact: true }).click();
  await page.getByRole("button", { name: "$1,420,000", exact: true }).click();
  await page.getByRole("switch", { name: "Show I read this as" }).click();
  const slider = page.getByRole("slider", { name: "Thinking time limit" });
  await slider.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByText("11 minutes")).toBeVisible();
  await page.getByRole("button", { name: "Seafoam", exact: true }).click();
  await expect(page.getByRole("button", { name: "Seafoam", exact: true })).toHaveAttribute("aria-pressed", "true");

  await page.reload();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Detailed", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "$1,420,000", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("switch", { name: "Show I read this as" })).toHaveAttribute("aria-checked", "false");
  await expect(page.getByText("11 minutes")).toBeVisible();
  await expect(page.getByRole("button", { name: "Seafoam", exact: true })).toHaveAttribute("aria-pressed", "true");
});

test("password_mismatch and the API errors", async ({ page }) => {
  await page.getByRole("button", { name: "Change password", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Change password" });
  await dialog.getByLabel("New password", { exact: true }).fill("new-password-1");
  await dialog.getByLabel("Confirm new password", { exact: true }).fill("something-else");
  await dialog.getByRole("button", { name: "Change password", exact: true }).click();
  const summary = dialog.locator('form > p[role="alert"]');
  await expect(summary).toHaveText("The new passwords don't match.");

  await dialog.getByLabel("Current password", { exact: true }).fill("wrong-password");
  await dialog.getByLabel("Confirm new password", { exact: true }).fill("new-password-1");
  await dialog.getByRole("button", { name: "Change password", exact: true }).click();
  await expect(summary).toHaveText("The current password isn't right.");

  await dialog.getByLabel("Current password", { exact: true }).fill("bella-forno");
  await dialog.getByRole("button", { name: "Change password", exact: true }).click();
  await expect(page.getByText("Password changed.")).toBeVisible();
  await expect(dialog).toBeHidden();
});

test("clear_memories forgets one, then everything", async ({ page }) => {
  const austin = "I mostly care about the Austin restaurants.";
  // Cancelling keeps the memory.
  await page.getByRole("button", { name: `Forget: ${austin}`, exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Forget this?" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByText(austin)).toBeVisible();
  // Forgetting removes just that one.
  await page.getByRole("button", { name: `Forget: ${austin}`, exact: true }).click();
  await page.getByRole("dialog", { name: "Forget this?" }).getByRole("button", { name: "Forget", exact: true }).click();
  await expect(page.getByText(austin)).toBeHidden();
  await expect(page.getByText('For me, "sales" means without delivery fees.')).toBeVisible();
  // Forgetting everything empties the list.
  await page.getByRole("button", { name: "Forget everything" }).click();
  await expect(page.getByRole("dialog", { name: "Forget everything?" })).toBeVisible();
  await page.getByRole("dialog", { name: "Forget everything?" }).getByRole("button", { name: "Forget everything", exact: true }).click();
  await expect(page.getByText("Nothing remembered yet.")).toBeVisible();
});

test("show_reading_hides_the_reading_line", async ({ page }) => {
  const reading = page.getByText("net sales, orders and average order");
  const toggle = page.getByRole("switch", { name: "Show I read this as" });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "false");

  await page.goto(`${CHAT}/chat/1`);
  await expect(page.getByRole("heading", { name: "How are we doing this month?" })).toBeVisible();
  // Only the reading line hides; the rest of the answer still renders.
  await expect(reading).toBeHidden();
  await expect(page.getByText("October is a good month so far")).toBeVisible();

  // The preference persists after reload.
  await page.reload();
  await expect(page.getByRole("heading", { name: "How are we doing this month?" })).toBeVisible();
  await expect(reading).toBeHidden();
  await expect(page.getByText("October is a good month so far")).toBeVisible();

  // Turning it back on restores the line.
  await page.goto(`${CHAT}/settings`);
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await page.goto(`${CHAT}/chat/1`);
  await expect(reading).toBeVisible();
});

test("sign_out returns to login", async ({ page }) => {
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(`${CHAT}/login`);
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
});
